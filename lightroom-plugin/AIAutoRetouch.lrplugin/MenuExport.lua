local LrDialogs = import "LrDialogs"
local LrTasks = import "LrTasks"

local BatchRunner = require "BatchRunner"
local Debug = require "Debug"
local Logger = require "Logger"

LrTasks.startAsyncTask(function()
    local ok, message = LrTasks.pcall(function()
        BatchRunner.finalExport()
    end)
    if not ok then
        Debug.fail(message)
        Logger.error(message)
        LrDialogs.message("AI Export Error", tostring(message) .. "\n\n" .. Debug.statusText(), "critical")
    end
end)
