local LrHttp = import "LrHttp"

local Debug = require "Debug"
local Json = require "Json"
local Logger = require "Logger"

local ServiceClient = {}

local function joinUrl(baseUrl, path)
    if baseUrl:sub(-1) == "/" then
        baseUrl = baseUrl:sub(1, -2)
    end
    if path:sub(1, 1) ~= "/" then
        path = "/" .. path
    end
    return baseUrl .. path
end

local function headers()
    return {
        { field = "Content-Type", value = "application/json" },
        { field = "Accept", value = "application/json" },
    }
end

local function previewText(text)
    local value = tostring(text or "")
    value = value:gsub("%s+", " ")
    if #value > 700 then
        return value:sub(1, 700) .. "..."
    end
    return value
end

local function decodeJson(method, url, response)
    if response == nil or response == "" then
        error("No response from local AI service: " .. url .. "\n请确认本地服务已启动，地址是否正确。")
    end
    local ok, result = pcall(function()
        return Json.decode(response)
    end)
    if ok then
        return result
    end
    local message = table.concat({
        "Invalid JSON response from local AI service.",
        "Method: " .. tostring(method),
        "URL: " .. tostring(url),
        "Decode error: " .. tostring(result),
        "Response preview: " .. previewText(response),
        "可能原因：服务未启动、接口路径不对、服务端报错返回了 HTML/纯文本，或请求参数导致 500。",
    }, "\n")
    Debug.fail(message)
    error(message)
end

function ServiceClient.getJson(baseUrl, path)
    local url = joinUrl(baseUrl, path)
    Logger.info("GET " .. url)
    Debug.http("GET", url, "request")
    local body = LrHttp.get(url, headers())
    Debug.http("GET", url, "response " .. tostring(#tostring(body or "")) .. " bytes")
    return decodeJson("GET", url, body)
end

function ServiceClient.postJson(baseUrl, path, payload)
    local url = joinUrl(baseUrl, path)
    local body = Json.encode(payload)
    Logger.info("POST " .. url)
    Debug.http("POST", url, "request " .. tostring(#body) .. " bytes")
    local response = LrHttp.post(url, body, headers())
    Debug.http("POST", url, "response " .. tostring(#tostring(response or "")) .. " bytes")
    return decodeJson("POST", url, response)
end

return ServiceClient
