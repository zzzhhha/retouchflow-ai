local LrTasks = import "LrTasks"

local Settings = require "Settings"

LrTasks.startAsyncTask(function()
    Settings.presentDialog("AI Auto Retouch Settings")
end)
