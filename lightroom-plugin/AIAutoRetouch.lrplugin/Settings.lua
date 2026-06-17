local LrBinding = import "LrBinding"
local LrDialogs = import "LrDialogs"
local LrFunctionContext = import "LrFunctionContext"
local LrPrefs = import "LrPrefs"
local LrView = import "LrView"

local Json = require "Json"

local Settings = {}
local prefs = LrPrefs.prefsForPlugin()

local scenes = {
    { title = "自动识别", value = "auto" },
    { title = "人像", value = "portrait" },
    { title = "婚纱", value = "wedding" },
    { title = "儿童", value = "children" },
    { title = "室内写真", value = "indoor_portrait" },
    { title = "户外逆光", value = "outdoor_backlight" },
    { title = "风景", value = "landscape" },
    { title = "花卉", value = "flower" },
    { title = "草地树木", value = "grass_tree" },
    { title = "森林", value = "forest" },
    { title = "城市建筑", value = "architecture" },
    { title = "日落晚霞", value = "sunset" },
    { title = "蓝天白云", value = "blue_sky" },
    { title = "夜景", value = "night" },
    { title = "美食", value = "food" },
    { title = "静物", value = "still_life" },
}

local aesthetics = {
    { title = "自然", value = "natural" },
    { title = "糖水片", value = "sweet" },
    { title = "质感片", value = "texture" },
    { title = "大师风", value = "master" },
    { title = "日系清透", value = "japanese_clear" },
    { title = "胶片感", value = "film" },
    { title = "商业干净", value = "commercial_clean" },
    { title = "纪实自然", value = "documentary" },
    { title = "暖调柔和", value = "warm_soft" },
    { title = "冷调通透", value = "cool_transparent" },
    { title = "高级灰", value = "high_gray" },
}

local editLevels = {
    { title = "基础修图", value = "basic" },
    { title = "基础修图 + 进阶建议", value = "basic_plus_advanced_suggestions" },
    { title = "基础修图 + 进阶执行", value = "basic_plus_advanced_execute" },
}

local retouchEngines = {
    { title = "Photoshop 精修（PSD/JPG）", value = "photoshop" },
    { title = "本地像素精修", value = "pixel" },
}

local retouchSourceFormats = {
    { title = "高质量 JPG", value = "JPEG" },
    { title = "16-bit TIFF", value = "TIFF" },
}

function Settings.getServiceUrl()
    return prefs.serviceUrl or "http://127.0.0.1:8765"
end

function Settings.getStyle()
    return prefs.style or "natural_portrait"
end

function Settings.getScene()
    return prefs.scene or "auto"
end

function Settings.getAesthetic()
    return prefs.aesthetic or "natural"
end

function Settings.getEditLevel()
    return prefs.editLevel or "basic"
end

function Settings.getUserSuggestion()
    return prefs.userSuggestion or ""
end

function Settings.getMaxReviewPasses()
    return tonumber(prefs.maxReviewPasses or 1)
end

function Settings.getFinalExportDir()
    return prefs.finalExportDir
end

function Settings.getEnablePixelRetouch()
    if prefs.enablePixelRetouch == nil then
        return true
    end
    return prefs.enablePixelRetouch == true
end

function Settings.getPixelRetouchStrength()
    return tonumber(prefs.pixelRetouchStrength or 0.18)
end

function Settings.getRetouchEngine()
    return prefs.retouchEngine or "photoshop"
end

function Settings.getRetouchSourceFormat()
    return prefs.retouchSourceFormat or "JPEG"
end

function Settings.getPhotoshopWaitSeconds()
    return tonumber(prefs.photoshopWaitSeconds or 60)
end

function Settings.getImportPixelRetouchResults()
    if prefs.importPixelRetouchResults == nil then
        return true
    end
    return prefs.importPixelRetouchResults == true
end

function Settings.getEnableDebugMode()
    return prefs.enableDebugMode == true
end

function Settings.setLastBatch(batchId, batchDir)
    prefs.lastBatchId = batchId
    prefs.lastBatchDir = batchDir
end

function Settings.getLastBatch()
    return prefs.lastBatchId, prefs.lastBatchDir
end

function Settings.setPendingPixelRetouch(report)
    if report == nil then
        prefs.pendingPixelRetouch = nil
    else
        prefs.pendingPixelRetouch = Json.encode(report)
    end
end

function Settings.getPendingPixelRetouch()
    local raw = prefs.pendingPixelRetouch
    if raw == nil or raw == "" then
        return nil
    end
    local ok, value = pcall(function()
        return Json.decode(raw)
    end)
    if ok then
        return value
    end
    prefs.pendingPixelRetouch = nil
    return nil
end

function Settings.clearPendingPixelRetouch()
    prefs.pendingPixelRetouch = nil
end

function Settings.presentDialog(title)
    local result = nil
    LrFunctionContext.callWithContext("ai-retouch-settings", function(context)
        local f = LrView.osFactory()
        local bind = LrView.bind
        local props = LrBinding.makePropertyTable(context)
        props.serviceUrl = Settings.getServiceUrl()
        props.style = Settings.getStyle()
        props.scene = Settings.getScene()
        props.aesthetic = Settings.getAesthetic()
        props.editLevel = Settings.getEditLevel()
        props.userSuggestion = Settings.getUserSuggestion()
        props.maxReviewPasses = Settings.getMaxReviewPasses()
        props.finalExportDir = Settings.getFinalExportDir() or ""
        props.enablePixelRetouch = Settings.getEnablePixelRetouch()
        props.pixelRetouchStrength = Settings.getPixelRetouchStrength()
        props.retouchEngine = Settings.getRetouchEngine()
        props.retouchSourceFormat = Settings.getRetouchSourceFormat()
        props.photoshopWaitSeconds = Settings.getPhotoshopWaitSeconds()
        props.importPixelRetouchResults = Settings.getImportPixelRetouchResults()
        props.enableDebugMode = Settings.getEnableDebugMode()

        local contents = f:column {
            bind_to_object = props,
            spacing = f:control_spacing(),
            f:row {
                f:static_text { title = "本地服务地址", width = 150 },
                f:edit_field { value = bind("serviceUrl"), width_in_chars = 36 },
            },
            f:row {
                f:static_text { title = "照片场景", width = 150 },
                f:popup_menu { value = bind("scene"), items = scenes },
            },
            f:row {
                f:static_text { title = "审美风格", width = 150 },
                f:popup_menu { value = bind("aesthetic"), items = aesthetics },
            },
            f:row {
                f:static_text { title = "处理层级", width = 150 },
                f:popup_menu { value = bind("editLevel"), items = editLevels },
            },
            f:row {
                f:static_text { title = "修图建议", width = 150 },
                f:edit_field { value = bind("userSuggestion"), width_in_chars = 36, height_in_lines = 3 },
            },
            f:row {
                f:static_text { title = "审核修正轮数(0-2)", width = 150 },
                f:edit_field { value = bind("maxReviewPasses"), width_in_chars = 8 },
            },
            f:row {
                f:static_text { title = "最终导出目录", width = 150 },
                f:edit_field { value = bind("finalExportDir"), width_in_chars = 36 },
            },
            f:row {
                f:static_text { title = "自动精修", width = 150 },
                f:checkbox { title = "导出高质量源图并执行精修", value = bind("enablePixelRetouch") },
            },
            f:row {
                f:static_text { title = "精修引擎", width = 150 },
                f:popup_menu { value = bind("retouchEngine"), items = retouchEngines },
            },
            f:row {
                f:static_text { title = "精修源格式", width = 150 },
                f:popup_menu { value = bind("retouchSourceFormat"), items = retouchSourceFormats },
            },
            f:row {
                f:static_text { title = "精修强度", width = 150 },
                f:edit_field { value = bind("pixelRetouchStrength"), width_in_chars = 8 },
            },
            f:row {
                f:static_text { title = "Photoshop等待(秒)", width = 150 },
                f:edit_field { value = bind("photoshopWaitSeconds"), width_in_chars = 8 },
            },
            f:row {
                f:static_text { title = "导入审核", width = 150 },
                f:checkbox { title = "导入精修结果用于人工确认", value = bind("importPixelRetouchResults") },
            },
            f:row {
                f:static_text { title = "Debug", width = 150 },
                f:checkbox { title = "开启调试日志和实时步骤状态", value = bind("enableDebugMode") },
            },
        }

        local button = LrDialogs.presentModalDialog {
            title = title or "AI 自动修图设置",
            contents = contents,
        }

        if button == "ok" then
            prefs.serviceUrl = props.serviceUrl
            prefs.style = props.style
            prefs.scene = props.scene
            prefs.aesthetic = props.aesthetic
            prefs.editLevel = props.editLevel
            prefs.userSuggestion = props.userSuggestion
            prefs.maxReviewPasses = tonumber(props.maxReviewPasses) or 1
            prefs.finalExportDir = props.finalExportDir
            prefs.enablePixelRetouch = props.enablePixelRetouch == true
            prefs.pixelRetouchStrength = tonumber(props.pixelRetouchStrength) or 0.18
            prefs.retouchEngine = props.retouchEngine or "photoshop"
            prefs.retouchSourceFormat = props.retouchSourceFormat or "JPEG"
            prefs.photoshopWaitSeconds = tonumber(props.photoshopWaitSeconds) or 60
            prefs.importPixelRetouchResults = props.importPixelRetouchResults == true
            prefs.enableDebugMode = props.enableDebugMode == true
            result = {
                serviceUrl = props.serviceUrl,
                style = props.style,
                scene = props.scene,
                aesthetic = props.aesthetic,
                editLevel = props.editLevel,
                userSuggestion = props.userSuggestion or "",
                maxReviewPasses = tonumber(props.maxReviewPasses) or 1,
                finalExportDir = props.finalExportDir,
                enablePixelRetouch = props.enablePixelRetouch == true,
                pixelRetouchStrength = tonumber(props.pixelRetouchStrength) or 0.18,
                retouchEngine = props.retouchEngine or "photoshop",
                retouchSourceFormat = props.retouchSourceFormat or "JPEG",
                photoshopWaitSeconds = tonumber(props.photoshopWaitSeconds) or 60,
                importPixelRetouchResults = props.importPixelRetouchResults == true,
                enableDebugMode = props.enableDebugMode == true,
            }
        end
    end)
    return result
end

return Settings
