local LrTasks = import "LrTasks"

local Debug = require "Debug"

LrTasks.startAsyncTask(function()
    Debug.showStatus()
end)
