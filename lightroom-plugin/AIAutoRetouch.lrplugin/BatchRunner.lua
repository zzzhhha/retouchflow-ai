local LrApplication = import "LrApplication"
local LrDate = import "LrDate"
local LrDialogs = import "LrDialogs"
local LrFileUtils = import "LrFileUtils"
local LrPathUtils = import "LrPathUtils"
local LrProgressScope = import "LrProgressScope"

local ApplyDevelop = require "ApplyDevelop"
local Debug = require "Debug"
local Export = require "Export"
local Json = require "Json"
local PhotoUtils = require "PhotoUtils"
local ServiceClient = require "ServiceClient"
local Settings = require "Settings"

local BatchRunner = {}

local function timestamp()
    return LrDate.timeToUserFormat(LrDate.currentTime(), "%Y%m%d-%H%M%S")
end

local function writeText(path, text)
    local file = io.open(path, "w")
    if file == nil then
        error("Unable to write file: " .. tostring(path))
    end
    file:write(text)
    file:close()
end

local function photosPayload(rendered)
    local photos = {}
    for _, item in ipairs(rendered) do
        photos[#photos + 1] = {
            photo_id = item.photo_id,
            file_name = item.file_name,
            preview_path = item.path,
            metadata = PhotoUtils.metadata(item.photo),
        }
    end
    return photos
end

local function byPhotoId(items, valueKey)
    local result = {}
    for _, item in ipairs(items or {}) do
        result[item.photo_id] = item[valueKey]
    end
    return result
end

local function mergeParams(params, deltas)
    local merged = {}
    for key, value in pairs(params or {}) do
        merged[key] = value
    end
    for key, value in pairs(deltas or {}) do
        merged[key] = tonumber(merged[key] or 0) + tonumber(value or 0)
    end
    return merged
end

local function plansById(plans)
    local result = {}
    for _, plan in ipairs(plans or {}) do
        result[plan.photo_id] = plan
    end
    return result
end

local function copyTable(value)
    local result = {}
    for key, item in pairs(value or {}) do
        result[key] = item
    end
    return result
end

local function updatePlansWithApplyResponse(currentPlans, applyPhotos)
    local updates = plansById(applyPhotos)
    local seen = {}
    local result = {}
    for _, plan in ipairs(currentPlans or {}) do
        local item = copyTable(plan)
        local update = updates[plan.photo_id]
        if update ~= nil then
            item.params = update.params or item.params
            item.lightroom_settings = update.lightroom_settings or item.lightroom_settings
            seen[plan.photo_id] = true
        end
        result[#result + 1] = item
    end
    for _, update in ipairs(applyPhotos or {}) do
        if not seen[update.photo_id] then
            result[#result + 1] = update
        end
    end
    return result
end

local function ensurePhotosSelected(photos)
    if #photos == 0 then
        LrDialogs.message("AI Auto Retouch", "请先在 Lightroom Library 里选择至少一张照片。", "info")
        return false
    end
    return true
end

local function fileExists(path)
    local file = io.open(path, "rb")
    if file ~= nil then
        file:close()
        return true
    end
    return false
end

local function fileStem(path)
    local name = LrPathUtils.leafName(path or "")
    local stem = name:gsub("%.[^%.]+$", "")
    if stem == nil or stem == "" then
        return "photo"
    end
    return stem
end

local function safeFilePart(value)
    local clean = tostring(value or "photo"):gsub("[^%w%-_]+", "_")
    if clean == "" then
        clean = "photo"
    end
    if #clean > 80 then
        clean = clean:sub(-80)
    end
    return clean
end

local function uniquePath(destDir, baseName, extension)
    local candidate = LrPathUtils.child(destDir, baseName .. extension)
    local index = 1
    while fileExists(candidate) do
        candidate = LrPathUtils.child(destDir, baseName .. "-" .. tostring(index) .. extension)
        index = index + 1
    end
    return candidate
end

local function retouchOperations(plan)
    local operations = {}
    local localAnalysis = plan and plan.local_analysis
    local operationPlans = localAnalysis and localAnalysis.operations
    for _, operation in ipairs(operationPlans or {}) do
        if operation.id ~= nil then
            operations[#operations + 1] = operation.id
        end
    end
    return operations
end

local function planUserSuggestion(plan, settings)
    local localAnalysis = plan and plan.local_analysis
    if localAnalysis ~= nil and localAnalysis.user_suggestion ~= nil then
        return localAnalysis.user_suggestion
    end
    return settings.userSuggestion or ""
end

local function importPhotos(catalog, paths)
    local imported = {}
    catalog:withWriteAccessDo("Import AI retouch results", function()
        for _, path in ipairs(paths or {}) do
            local ok, photo = pcall(function()
                return catalog:addPhoto(path)
            end)
            if ok and photo ~= nil then
                imported[#imported + 1] = photo
            end
        end
        if #imported > 0 then
            pcall(function()
                catalog:setSelectedPhotos(imported[1], imported)
            end)
        end
    end)
    return imported
end

local function copyPendingResults(pending, destDir)
    Export.ensureDir(destDir)
    local copied = {}
    for index, item in ipairs(pending.results or {}) do
        local sourcePath = item.output_path
        if sourcePath ~= nil and sourcePath ~= "" and fileExists(sourcePath) then
            local baseName = safeFilePart(fileStem(item.file_name or sourcePath))
            local destPath = uniquePath(destDir, string.format("%03d-%s-AI", index, baseName), ".jpg")
            Export.copyFile(sourcePath, destPath)
            copied[#copied + 1] = {
                photo_id = item.photo_id,
                file_name = item.file_name,
                source_path = sourcePath,
                final_path = destPath,
            }
        end
    end
    return copied
end

local function postExportReport(serviceUrl, batchId, payload)
    ServiceClient.postJson(serviceUrl, "/v1/batches/export-report", {
        batch_id = batchId,
        payload = payload,
    })
end

local function retouchEngine(settings)
    local engine = tostring(settings.retouchEngine or "photoshop")
    if engine ~= "photoshop" and engine ~= "pixel" then
        return "photoshop"
    end
    return engine
end

local function retouchSourceFormat(settings)
    local format = tostring(settings.retouchSourceFormat or "JPEG")
    if format ~= "TIFF" then
        return "JPEG"
    end
    return "TIFF"
end

local function retouchMode(engine, state)
    if engine == "photoshop" then
        return "photoshop-retouch-" .. state
    end
    return "pixel-retouch-" .. state
end

local function loadAnalyzePlans(settings, batchId)
    local okAnalyze, analyze = pcall(function()
        return ServiceClient.getJson(settings.serviceUrl, "/api/runs/" .. tostring(batchId) .. "/analyze.json")
    end)
    if not okAnalyze then
        return {}
    end
    return analyze and analyze.payload and analyze.payload.photos or analyze and analyze.photos or {}
end

local function stageRetouch(catalog, photos, settings, batchId, batchDir, progress, plans)
    local engine = retouchEngine(settings)
    local sourceFormat = retouchSourceFormat(settings)
    local sourceDir = LrPathUtils.child(batchDir, engine .. "_sources")
    local outputDir = LrPathUtils.child(batchDir, engine .. "_retouched")
    local psdDir = LrPathUtils.child(batchDir, "photoshop_psd")
    local manifestsDir = LrPathUtils.child(batchDir, "manifests")
    LrFileUtils.createAllDirectories(outputDir)
    LrFileUtils.createAllDirectories(psdDir)
    LrFileUtils.createAllDirectories(manifestsDir)

    Debug.progress(progress, "Export retouch sources", "Exporting high quality " .. sourceFormat .. " files")
    local rendered = Export.retouchSources(photos, sourceDir, sourceFormat, progress)
    plans = plans or loadAnalyzePlans(settings, batchId)
    local planById = plansById(plans)
    local results = {}
    local importPaths = {}
    local completedCount = 0
    local pendingCount = 0
    local failedCount = 0

    for index, item in ipairs(rendered) do
        local plan = planById[item.photo_id] or {}
        local scene = plan.detected_scene or settings.scene or "auto"
        local outputName = string.format("%03d-%s-AI.jpg", index, safeFilePart(fileStem(item.file_name)))
        local outputPath = uniquePath(outputDir, outputName:gsub("%.jpg$", ""), ".jpg")
        local suffix = engine .. "-retouch-" .. tostring(index)
        local request = {
            batch_id = batchId,
            photo_id = item.photo_id,
            input_path = item.path,
            output_path = outputPath,
            scene = scene,
            aesthetic = settings.aesthetic or "natural",
            operations = retouchOperations(plan),
            strength = tonumber(settings.pixelRetouchStrength or 0.18),
            user_suggestion = planUserSuggestion(plan, settings),
        }
        local endpoint = "/v1/photos/pixel-retouch"
        if engine == "photoshop" then
            endpoint = "/v1/photos/photoshop-retouch"
            request.psd_path = uniquePath(psdDir, outputName:gsub("%.jpg$", ""), ".psd")
            request.run = true
            request.wait_seconds = math.max(0, tonumber(settings.photoshopWaitSeconds or 60))
        end

        writeText(LrPathUtils.child(manifestsDir, suffix .. "-request.json"), Json.encode(request))
        Debug.progress(progress, "Run " .. engine .. " retouch " .. tostring(index) .. "/" .. tostring(#rendered), tostring(item.file_name))
        local response = ServiceClient.postJson(settings.serviceUrl, endpoint, request)
        writeText(LrPathUtils.child(manifestsDir, suffix .. "-response.json"), Json.encode(response))

        local status = tostring(response.status or "")
        local actualOutput = response.output_path or outputPath
        if status == "failed" then
            failedCount = failedCount + 1
        elseif actualOutput ~= nil and actualOutput ~= "" and fileExists(actualOutput) then
            completedCount = completedCount + 1
            importPaths[#importPaths + 1] = actualOutput
        else
            pendingCount = pendingCount + 1
        end

        local result = {
            photo_id = item.photo_id,
            file_name = item.file_name,
            input_path = item.path,
            output_path = actualOutput,
            scene = scene,
            status = status,
            engine = engine,
            operations_applied = response.operations_applied or {},
            operations_planned = response.operations_planned or {},
            mask_assets = response.mask_assets or {},
            job = response.job,
            psd_path = response.psd_path,
        }
        results[#results + 1] = result
    end

    local imported = {}
    if settings.importPixelRetouchResults and #importPaths > 0 then
        Debug.progress(progress, "Import retouched files", "Importing generated retouch results for review")
        imported = importPhotos(catalog, importPaths)
    end

    return {
        batch_id = batchId,
        batch_dir = batchDir,
        retouch_engine = engine,
        source_format = sourceFormat,
        source_dir = sourceDir,
        output_dir = outputDir,
        psd_dir = psdDir,
        final_export_dir = settings.finalExportDir,
        result_count = #results,
        completed_count = completedCount,
        pending_count = pendingCount,
        failed_count = failedCount,
        imported_count = #imported,
        results = results,
    }
end

local function saveStagedRetouch(settings, batchId, staged, state)
    Settings.setPendingPixelRetouch(staged)
    postExportReport(settings.serviceUrl, batchId, {
        mode = retouchMode(staged.retouch_engine, state),
        retouch_engine = staged.retouch_engine,
        source_format = staged.source_format,
        staged_count = staged.result_count,
        completed_count = staged.completed_count,
        pending_count = staged.pending_count,
        failed_count = staged.failed_count,
        imported_count = staged.imported_count,
        staged_output_dir = staged.output_dir,
        psd_dir = staged.psd_dir,
        final_export_dir = settings.finalExportDir,
    })
end

local function stagedRetouchMessage(staged)
    local engineLabel = staged.retouch_engine == "photoshop" and "Photoshop 精修" or "本地像素精修"
    if staged.completed_count > 0 then
        return engineLabel
            .. "结果已生成"
            .. (staged.imported_count > 0 and "并导入 Lightroom 供审核。" or "，请到临时目录查看。")
            .. "\n完成: " .. tostring(staged.completed_count)
            .. "，待执行: " .. tostring(staged.pending_count)
            .. "，失败: " .. tostring(staged.failed_count)
            .. "\n确认满意后再次运行 AI Export 完成最终导出。\nBatch: " .. tostring(staged.batch_id)
    end
    return engineLabel
        .. "任务已创建，但还没有可导入的输出文件。"
        .. "\n待执行: " .. tostring(staged.pending_count)
        .. "，失败: " .. tostring(staged.failed_count)
        .. "\n请检查 Debug 状态或 Photoshop 作业队列。\n目录: " .. tostring(staged.output_dir)
end

function BatchRunner.autoRetouch()
    Debug.start("AI Auto Retouch", "")
    local settings = Settings.presentDialog("AI Auto Retouch")
    if settings == nil then
        Debug.finish("Canceled settings dialog")
        return
    end

    local catalog = LrApplication.activeCatalog()
    local photos = catalog:getTargetPhotos()
    if not ensurePhotosSelected(photos) then
        return
    end

    Debug.step("Health check", settings.serviceUrl)
    local health = ServiceClient.getJson(settings.serviceUrl, "/health")
    if health.status ~= "ok" then
        error("Local AI service is not healthy")
    end

    local batchId = timestamp()
    Debug.setBatch(batchId)
    local batchDir = Export.batchRoot(batchId)
    local previewsDir = LrPathUtils.child(batchDir, "original_previews")
    local proofsRoot = LrPathUtils.child(batchDir, "proofs")
    local manifestsDir = LrPathUtils.child(batchDir, "manifests")
    LrFileUtils.createAllDirectories(manifestsDir)
    Settings.setLastBatch(batchId, batchDir)

    local progress = LrProgressScope {
        title = "AI Auto Retouch",
        caption = "Exporting Lightroom previews...",
    }

    Debug.progress(progress, "1/7 Export previews", "Exporting Lightroom previews")
    local renderedPreviews = Export.previews(photos, previewsDir, progress)
    local analyzeRequest = {
        batch_id = batchId,
        style = settings.style,
        scene = settings.scene,
        aesthetic = settings.aesthetic,
        edit_level = settings.editLevel,
        user_suggestion = settings.userSuggestion or "",
        photos = photosPayload(renderedPreviews),
    }
    writeText(LrPathUtils.child(manifestsDir, "analyze-request.json"), Json.encode(analyzeRequest))

    Debug.progress(progress, "2/7 Analyze previews", "Calling /v1/batches/analyze")
    local analyzeResponse = ServiceClient.postJson(settings.serviceUrl, "/v1/batches/analyze", analyzeRequest)
    writeText(LrPathUtils.child(manifestsDir, "analyze-response.json"), Json.encode(analyzeResponse))

    local photosById = PhotoUtils.indexById(photos)
    local currentPlans = analyzeResponse.photos or {}

    Debug.progress(progress, "3/7 Apply Lightroom settings", "Applying initial Develop settings")
    ApplyDevelop.applyPlans(catalog, photosById, currentPlans, batchId, settings.style, "initial", nil, progress)

    local maxCorrections = math.max(0, math.min(tonumber(settings.maxReviewPasses or 2), 2))
    local correctionsApplied = 0
    local passIndex = 1
    local finalReview = nil
    while true do
        Debug.progress(progress, "4/7 Export proof", "Pass " .. tostring(passIndex))
        local proofDir = LrPathUtils.child(proofsRoot, "pass-" .. tostring(passIndex))
        local renderedProofs = Export.proofs(photos, proofDir, progress)
        local proofMap = byPhotoId(renderedProofs, "path")
        local previewMap = byPhotoId(renderedPreviews, "path")
        local planMap = plansById(currentPlans)

        local reviewPhotos = {}
        for _, photo in ipairs(photos) do
            local photoId = PhotoUtils.photoId(photo)
            reviewPhotos[#reviewPhotos + 1] = {
                photo_id = photoId,
                before_path = previewMap[photoId],
                after_path = proofMap[photoId],
                params = planMap[photoId] and planMap[photoId].params or {},
            }
        end

        local reviewRequest = {
            batch_id = batchId,
            style = settings.style,
            scene = settings.scene,
            aesthetic = settings.aesthetic,
            edit_level = settings.editLevel,
            user_suggestion = settings.userSuggestion or "",
            pass_index = passIndex,
            photos = reviewPhotos,
        }
        writeText(LrPathUtils.child(manifestsDir, "review-pass-" .. tostring(passIndex) .. "-request.json"), Json.encode(reviewRequest))

        Debug.progress(progress, "5/7 Review proof", "Calling /v1/batches/review pass " .. tostring(passIndex))
        finalReview = ServiceClient.postJson(settings.serviceUrl, "/v1/batches/review", reviewRequest)
        writeText(LrPathUtils.child(manifestsDir, "review-pass-" .. tostring(passIndex) .. "-response.json"), Json.encode(finalReview))

        local scoreById = {}
        for _, result in ipairs(finalReview.photos or {}) do
            scoreById[result.photo_id] = result.score
        end
        ApplyDevelop.updateScores(catalog, photosById, batchId, settings.style, scoreById)

        if finalReview.passed or correctionsApplied >= maxCorrections then
            break
        end

        Debug.progress(progress, "6/7 Apply corrections", "Applying AI correction deltas")
        local mergedPhotos = {}
        for _, result in ipairs(finalReview.photos or {}) do
            local current = planMap[result.photo_id]
            if current ~= nil then
                mergedPhotos[#mergedPhotos + 1] = {
                    photo_id = result.photo_id,
                    params = mergeParams(current.params, result.deltas),
                }
            end
        end
        if #mergedPhotos == 0 then
            break
        end

        local applyResponse = ServiceClient.postJson(settings.serviceUrl, "/v1/batches/apply-plan", {
            batch_id = batchId,
            photos = mergedPhotos,
        })
        currentPlans = updatePlansWithApplyResponse(currentPlans, applyResponse.photos or {})
        correctionsApplied = correctionsApplied + 1
        ApplyDevelop.applyPlans(catalog, photosById, currentPlans, batchId, settings.style, "review-" .. tostring(correctionsApplied), nil, progress)
        passIndex = passIndex + 1
    end

    local staged = nil
    if settings.enablePixelRetouch then
        Debug.progress(progress, "7/7 Precision retouch", "Export high quality files and run " .. retouchEngine(settings))
        staged = stageRetouch(catalog, photos, settings, batchId, batchDir, progress, currentPlans)
        saveStagedRetouch(settings, batchId, staged, "staged")
    end

    progress:done()
    local score = finalReview and finalReview.score or 0
    local message = "批量初修完成。\nBatch: " .. batchId .. "\nScore: " .. tostring(score) .. "\n临时文件: " .. batchDir
    if staged ~= nil then
        message = message .. "\n\n" .. stagedRetouchMessage(staged)
    end
    Debug.finish("Auto retouch finished. Score: " .. tostring(score))
    LrDialogs.message("AI Auto Retouch", message, "info")
end

function BatchRunner.finalExport()
    Debug.start("AI Export", "")
    local settings = Settings.presentDialog("AI Export")
    if settings == nil then
        Debug.finish("Canceled settings dialog")
        return
    end

    local destDir = settings.finalExportDir
    if destDir == nil or destDir == "" then
        LrDialogs.message("AI Export", "请先在设置里填写最终导出目录。", "warning")
        return
    end

    local pending = Settings.getPendingPixelRetouch()
    if settings.enablePixelRetouch and pending ~= nil and pending.results ~= nil and #pending.results > 0 then
        Debug.setBatch(pending.batch_id or "")
        Debug.step("Pending retouch", "Waiting for manual confirmation")
        local confirmed = LrDialogs.confirm(
            "AI Export",
            "检测到 " .. tostring(#pending.results) .. " 张待确认的精修结果。\n如果已经在 Lightroom 中检查满意，点击“导出”复制到最终目录。\nBatch: " .. tostring(pending.batch_id),
            "导出"
        )
        if confirmed == "ok" or confirmed == true then
            Debug.step("Finalize pending results", "Copying staged files to final export directory")
            local copied = copyPendingResults(pending, destDir)
            postExportReport(settings.serviceUrl, pending.batch_id or Settings.getLastBatch() or timestamp(), {
                mode = retouchMode(pending.retouch_engine, "finalized"),
                retouch_engine = pending.retouch_engine,
                exported_count = #copied,
                export_dir = destDir,
                staged_output_dir = pending.output_dir,
                psd_dir = pending.psd_dir,
                files = copied,
            })
            Settings.clearPendingPixelRetouch()
            Debug.finish("Pending retouch finalized: " .. tostring(#copied))
            LrDialogs.message("AI Export", "精修最终导出完成: " .. tostring(#copied) .. " 张。", "info")
            return
        end
        Debug.finish("Pending retouch kept for later confirmation")
        LrDialogs.message("AI Export", "已保留待确认的精修结果，未执行最终导出。", "info")
        return
    end

    local catalog = LrApplication.activeCatalog()
    local photos = catalog:getTargetPhotos()
    if not ensurePhotosSelected(photos) then
        return
    end

    local batchId, batchDir = Settings.getLastBatch()
    if batchId == nil or batchId == "" then
        batchId = timestamp()
        batchDir = Export.batchRoot(batchId)
        Settings.setLastBatch(batchId, batchDir)
    end
    if batchDir == nil or batchDir == "" then
        batchDir = Export.batchRoot(batchId)
        Settings.setLastBatch(batchId, batchDir)
    end
    Debug.setBatch(batchId)

    local progress = LrProgressScope {
        title = "AI Export",
        caption = "Preparing final export...",
    }
    if settings.enablePixelRetouch then
        Debug.progress(progress, "1/4 Health check", settings.serviceUrl)
        local health = ServiceClient.getJson(settings.serviceUrl, "/health")
        if health.status ~= "ok" then
            error("Local AI service is not healthy")
        end

        Debug.progress(progress, "2/4 Precision retouch", "Export sources and run " .. retouchEngine(settings))
        local staged = stageRetouch(catalog, photos, settings, batchId, batchDir, progress, nil)
        progress:done()

        if settings.importPixelRetouchResults then
            saveStagedRetouch(settings, batchId, staged, "staged")
            LrDialogs.message("AI Export", stagedRetouchMessage(staged), "info")
            Debug.finish("Retouch staged for manual review")
            return
        end

        local copied = copyPendingResults(staged, destDir)
        postExportReport(settings.serviceUrl, batchId, {
            mode = retouchMode(staged.retouch_engine, "direct"),
            retouch_engine = staged.retouch_engine,
            exported_count = #copied,
            export_dir = destDir,
            staged_output_dir = staged.output_dir,
            psd_dir = staged.psd_dir,
            files = copied,
        })
        Debug.finish("Retouch direct export finished: " .. tostring(#copied))
        LrDialogs.message("AI Export", "精修导出完成: " .. tostring(#copied) .. " 张。", "info")
        return
    end

    Debug.progress(progress, "Export final files", "Exporting final Lightroom files")
    local exported = Export.finalFiles(photos, destDir, "JPEG", progress)
    progress:done()

    postExportReport(settings.serviceUrl, batchId, {
        mode = "develop-only",
        exported_count = #exported,
        export_dir = destDir,
    })

    Debug.finish("Develop-only final export finished: " .. tostring(#exported))
    LrDialogs.message("AI Export", "导出完成: " .. tostring(#exported) .. " 张。", "info")
end

function BatchRunner.reviewCurrentBatch()
    local lastBatchId, lastBatchDir = Settings.getLastBatch()
    if lastBatchId == nil or lastBatchDir == nil then
        LrDialogs.message("AI Review", "没有找到上一轮 AI Auto Retouch 批次。", "info")
        return
    end
    LrDialogs.message("AI Review", "上一轮批次: " .. tostring(lastBatchId) .. "\n目录: " .. tostring(lastBatchDir), "info")
end

return BatchRunner
