local LrDialogs = import "LrDialogs"
local LrFileUtils = import "LrFileUtils"
local LrPathUtils = import "LrPathUtils"
local LrPrefs = import "LrPrefs"

local Json = require "Json"
local Logger = require "Logger"

local Debug = {}
local prefs = LrPrefs.prefsForPlugin()

local current = {
    workflow = "",
    batch_id = "",
    step = "",
    detail = "",
    status = "idle",
    started_at = "",
    updated_at = "",
    log_path = "",
    status_path = "",
}

local function now()
    return os.date("%Y-%m-%d %H:%M:%S")
end

local function debugRoot()
    local root = LrPathUtils.child(LrPathUtils.getStandardFilePath("temp"), "ai-lightroom-retouch")
    local path = LrPathUtils.child(root, "debug")
    LrFileUtils.createAllDirectories(path)
    return path
end

local function logPath()
    return LrPathUtils.child(debugRoot(), "debug.log")
end

local function statusPath()
    return LrPathUtils.child(debugRoot(), "last-status.json")
end

local function appendFile(path, text)
    local file = io.open(path, "a")
    if file == nil then
        return
    end
    file:write(text)
    file:close()
end

local function writeFile(path, text)
    local file = io.open(path, "w")
    if file == nil then
        return
    end
    file:write(text)
    file:close()
end

local function tail(path, limit)
    local file = io.open(path, "r")
    if file == nil then
        return ""
    end
    local lines = {}
    for line in file:lines() do
        lines[#lines + 1] = line
        if #lines > limit then
            table.remove(lines, 1)
        end
    end
    file:close()
    return table.concat(lines, "\n")
end

local function persist()
    current.updated_at = now()
    current.log_path = logPath()
    current.status_path = statusPath()
    local ok, encoded = pcall(function()
        return Json.encode(current)
    end)
    if ok then
        writeFile(statusPath(), encoded)
    end
end

function Debug.enabled()
    return prefs.enableDebugMode == true
end

function Debug.start(workflow, batchId)
    current.workflow = tostring(workflow or "")
    current.batch_id = tostring(batchId or "")
    current.step = "start"
    current.detail = ""
    current.status = "running"
    current.started_at = now()
    current.updated_at = current.started_at
    persist()
    if Debug.enabled() then
        appendFile(logPath(), "\n[" .. current.started_at .. "] START " .. current.workflow .. " batch=" .. current.batch_id .. "\n")
    end
end

function Debug.setBatch(batchId)
    current.batch_id = tostring(batchId or "")
    persist()
end

function Debug.step(step, detail)
    current.step = tostring(step or "")
    current.detail = tostring(detail or "")
    current.status = "running"
    persist()
    local line = "[" .. current.updated_at .. "] STEP " .. current.workflow .. " / " .. current.step .. " - " .. current.detail
    Logger.info(line)
    if Debug.enabled() then
        appendFile(logPath(), line .. "\n")
    end
end

function Debug.progress(progress, step, detail)
    Debug.step(step, detail)
    if progress then
        progress:setCaption(tostring(step or "") .. " - " .. tostring(detail or ""))
    end
end

function Debug.http(method, url, detail)
    local message = tostring(method or "") .. " " .. tostring(url or "")
    if detail ~= nil and detail ~= "" then
        message = message .. " - " .. tostring(detail)
    end
    Debug.step("HTTP", message)
end

function Debug.finish(detail)
    current.status = "finished"
    current.step = "finish"
    current.detail = tostring(detail or "")
    persist()
    if Debug.enabled() then
        appendFile(logPath(), "[" .. current.updated_at .. "] FINISH " .. current.workflow .. " - " .. current.detail .. "\n")
    end
end

function Debug.fail(message)
    current.status = "failed"
    current.step = current.step ~= "" and current.step or "error"
    current.detail = tostring(message or "")
    persist()
    Logger.error(current.detail)
    appendFile(logPath(), "[" .. current.updated_at .. "] ERROR " .. current.workflow .. " / " .. current.step .. " - " .. current.detail .. "\n")
end

function Debug.statusText()
    local lines = {
        "Status: " .. tostring(current.status),
        "Workflow: " .. tostring(current.workflow),
        "Batch: " .. tostring(current.batch_id),
        "Step: " .. tostring(current.step),
        "Detail: " .. tostring(current.detail),
        "Updated: " .. tostring(current.updated_at),
        "Log: " .. logPath(),
        "",
        "Recent log:",
        tail(logPath(), 18),
    }
    return table.concat(lines, "\n")
end

function Debug.showStatus()
    LrDialogs.message("AI Auto Retouch Debug", Debug.statusText(), "info")
end

return Debug
