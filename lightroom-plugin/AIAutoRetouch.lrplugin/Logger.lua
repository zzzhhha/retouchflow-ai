local LrLogger = import "LrLogger"

local logger = LrLogger("AIAutoRetouch")
logger:enable("logfile")

local Logger = {}

function Logger.info(message)
    logger:info(tostring(message))
end

function Logger.warn(message)
    logger:warn(tostring(message))
end

function Logger.error(message)
    logger:error(tostring(message))
end

function Logger.trace(message)
    logger:trace(tostring(message))
end

return Logger
