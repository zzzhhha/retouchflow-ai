local LrPathUtils = import "LrPathUtils"
local LrTasks = import "LrTasks"

local PhotoUtils = {}

local function safeCall(fn)
    local ok, value = LrTasks.pcall(fn)
    if ok then
        return value
    end
    return nil
end

function PhotoUtils.raw(photo, key)
    return safeCall(function()
        return photo:getRawMetadata(key)
    end)
end

function PhotoUtils.formatted(photo, key)
    return safeCall(function()
        return photo:getFormattedMetadata(key)
    end)
end

function PhotoUtils.photoId(photo)
    local uuid = PhotoUtils.raw(photo, "uuid")
    if uuid ~= nil and uuid ~= "" then
        return tostring(uuid)
    end

    local path = PhotoUtils.raw(photo, "path")
    if path ~= nil and path ~= "" then
        return tostring(path)
    end

    return tostring(photo)
end

function PhotoUtils.fileName(photo)
    local name = PhotoUtils.formatted(photo, "fileName")
    if name ~= nil and name ~= "" then
        return tostring(name)
    end

    local path = PhotoUtils.raw(photo, "path")
    if path ~= nil and path ~= "" then
        return LrPathUtils.leafName(path)
    end

    return PhotoUtils.photoId(photo) .. ".jpg"
end

function PhotoUtils.metadata(photo)
    return {
        camera = PhotoUtils.raw(photo, "cameraModel") or PhotoUtils.formatted(photo, "camera") or "",
        lens = PhotoUtils.raw(photo, "lens") or PhotoUtils.formatted(photo, "lens") or "",
        iso = tonumber(PhotoUtils.raw(photo, "isoSpeedRating") or 0),
        aperture = tonumber(PhotoUtils.raw(photo, "aperture") or 0),
        shutter = tostring(PhotoUtils.formatted(photo, "shutterSpeed") or ""),
        focal_length = tonumber(PhotoUtils.raw(photo, "focalLength") or 0),
    }
end

function PhotoUtils.indexById(photos)
    local byId = {}
    for _, photo in ipairs(photos) do
        byId[PhotoUtils.photoId(photo)] = photo
    end
    return byId
end

return PhotoUtils
