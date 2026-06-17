local LrApplication = import "LrApplication"
local LrTasks = import "LrTasks"

local Json = require "Json"
local Logger = require "Logger"

local ApplyDevelop = {}

local function copyTable(source)
    local result = {}
    if source == nil then
        return result
    end
    for key, value in pairs(source) do
        result[key] = value
    end
    return result
end

local function clamp(value, low, high)
    value = tonumber(value)
    if value == nil then
        return nil
    end
    if value < low then
        return low
    end
    if value > high then
        return high
    end
    return value
end

local function safeDevelopSettings(photo)
    local ok, settings = LrTasks.pcall(function()
        return photo:getDevelopSettings()
    end)
    if ok and settings ~= nil then
        return settings
    end
    return {}
end

local function mergedDevelopSettings(photo, incoming)
    local current = safeDevelopSettings(photo)
    local settings = copyTable(current)

    for key, value in pairs(incoming or {}) do
        if key ~= "TemperatureDelta" and key ~= "Tint" then
            settings[key] = value
        end
    end

    local tempDelta = tonumber(incoming and incoming.TemperatureDelta)
    local currentTemp = tonumber(current.Temperature)
    if tempDelta ~= nil and tempDelta ~= 0 and currentTemp ~= nil then
        settings.Temperature = clamp(currentTemp + tempDelta, 2000, 50000)
        settings.WhiteBalance = "Custom"
    end

    local tintDelta = tonumber(incoming and incoming.Tint)
    local currentTint = tonumber(current.Tint) or 0
    if tintDelta ~= nil and tintDelta ~= 0 then
        settings.Tint = clamp(currentTint + tintDelta, -150, 150)
        settings.WhiteBalance = "Custom"
    end

    settings.TemperatureDelta = nil
    return settings
end

local function presetName(batchId, photoId, passLabel)
    local cleanPhotoId = tostring(photoId):gsub("[^%w%-_]", "_")
    if #cleanPhotoId > 40 then
        cleanPhotoId = cleanPhotoId:sub(-40)
    end
    return "AI " .. tostring(batchId) .. " " .. tostring(passLabel or "pass") .. " " .. cleanPhotoId
end

local function createPreset(name, settings)
    local ok, preset = LrTasks.pcall(function()
        return LrApplication.addDevelopPresetForPlugin(_PLUGIN, name, settings)
    end)
    if not ok or preset == nil then
        error("Unable to create Lightroom develop preset: " .. tostring(preset))
    end
    return preset
end

local function applyPreset(photo, preset)
    local ok, message = LrTasks.pcall(function()
        return photo:applyDevelopPreset(preset)
    end)
    if ok then
        return
    end

    local okWithPlugin, pluginMessage = LrTasks.pcall(function()
        return photo:applyDevelopPreset(preset, _PLUGIN)
    end)
    if not okWithPlugin then
        error("Unable to apply Lightroom develop preset: " .. tostring(message or pluginMessage))
    end
end

local function createBeforeSnapshot(photo, batchId)
    LrTasks.pcall(function()
        photo:createDevelopSnapshot("AI Before " .. tostring(batchId), false)
    end)
end

local function setPluginMetadata(photo, batchId, style, score, params)
    LrTasks.pcall(function()
        photo:setPropertyForPlugin(_PLUGIN, "aiBatchId", tostring(batchId))
        photo:setPropertyForPlugin(_PLUGIN, "aiStyle", tostring(style or ""))
        if score ~= nil then
            photo:setPropertyForPlugin(_PLUGIN, "aiScore", tostring(score))
        end
        if params ~= nil then
            photo:setPropertyForPlugin(_PLUGIN, "aiParams", Json.encode(params))
        end
    end)
end

function ApplyDevelop.applyPlans(catalog, photosById, plans, batchId, style, passLabel, scoreById, progress)
    catalog:withWriteAccessDo("AI Auto Retouch", function()
        for index, plan in ipairs(plans or {}) do
            local photo = photosById[plan.photo_id]
            if photo ~= nil then
                if passLabel == "initial" then
                    createBeforeSnapshot(photo, batchId)
                end

                local settings = mergedDevelopSettings(photo, plan.lightroom_settings)
                local preset = createPreset(presetName(batchId, plan.photo_id, passLabel), settings)
                applyPreset(photo, preset)
                setPluginMetadata(photo, batchId, style, scoreById and scoreById[plan.photo_id], plan.params)
                Logger.info("Applied AI settings to photo " .. tostring(plan.photo_id))
            end

            if progress then
                progress:setPortionComplete(index, #(plans or {}))
            end
        end
    end)
end

function ApplyDevelop.updateScores(catalog, photosById, batchId, style, scoreById)
    catalog:withWriteAccessDo("AI Auto Retouch Scores", function()
        for photoId, score in pairs(scoreById or {}) do
            local photo = photosById[photoId]
            if photo ~= nil then
                setPluginMetadata(photo, batchId, style, score, nil)
            end
        end
    end)
end

return ApplyDevelop
