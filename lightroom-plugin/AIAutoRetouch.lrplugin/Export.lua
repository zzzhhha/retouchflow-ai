local LrExportSession = import "LrExportSession"
local LrFileUtils = import "LrFileUtils"
local LrPathUtils = import "LrPathUtils"

local PhotoUtils = require "PhotoUtils"

local Export = {}

function Export.ensureDir(path)
    LrFileUtils.createAllDirectories(path)
    return path
end

function Export.batchRoot(batchId)
    local temp = LrPathUtils.getStandardFilePath("temp")
    local root = LrPathUtils.child(temp, "ai-lightroom-retouch")
    return LrPathUtils.child(root, batchId)
end

local function commonJpegSettings(destDir, longEdge)
    return {
        LR_export_destinationType = "specificFolder",
        LR_export_destinationPathPrefix = destDir,
        LR_export_useSubfolder = false,
        LR_collisionHandling = "rename",
        LR_format = "JPEG",
        LR_jpeg_quality = 0.8,
        LR_export_colorSpace = "sRGB",
        LR_size_doConstrain = true,
        LR_size_resizeType = "longEdge",
        LR_size_maxHeight = longEdge,
        LR_size_maxWidth = longEdge,
        LR_size_units = "pixels",
        LR_size_doNotEnlarge = true,
        LR_outputSharpeningOn = false,
        LR_minimizeEmbeddedMetadata = true,
        LR_removeLocationMetadata = true,
    }
end

local function exportRenditions(photos, destDir, exportSettings, progress)
    Export.ensureDir(destDir)

    local session = LrExportSession {
        photosToExport = photos,
        exportSettings = exportSettings,
    }

    local rendered = {}
    local index = 0
    for _, rendition in session:renditions { stopIfCanceled = true } do
        index = index + 1
        if progress then
            progress:setPortionComplete(index - 1, #photos)
        end
        local success, pathOrMessage = rendition:waitForRender()
        if not success then
            error("Lightroom export failed: " .. tostring(pathOrMessage))
        end
        local photo = rendition.photo or photos[index]
        rendered[#rendered + 1] = {
            photo = photo,
            photo_id = PhotoUtils.photoId(photo),
            file_name = PhotoUtils.fileName(photo),
            path = pathOrMessage,
        }
        if progress then
            progress:setPortionComplete(index, #photos)
        end
    end

    return rendered
end

function Export.previews(photos, destDir, progress)
    return exportRenditions(photos, destDir, commonJpegSettings(destDir, 1600), progress)
end

function Export.proofs(photos, destDir, progress)
    return exportRenditions(photos, destDir, commonJpegSettings(destDir, 1600), progress)
end

function Export.retouchSources(photos, destDir, format, progress)
    Export.ensureDir(destDir)
    local exportFormat = format or "JPEG"
    local settings = {
        LR_export_destinationType = "specificFolder",
        LR_export_destinationPathPrefix = destDir,
        LR_export_useSubfolder = false,
        LR_collisionHandling = "rename",
        LR_format = exportFormat,
        LR_jpeg_quality = 0.95,
        LR_export_colorSpace = "sRGB",
        LR_size_doConstrain = false,
        LR_outputSharpeningOn = false,
        LR_minimizeEmbeddedMetadata = false,
        LR_removeLocationMetadata = true,
    }
    if exportFormat == "TIFF" then
        settings.LR_tiff_bitDepth = 16
        settings.LR_tiff_compressionMethod = "compressionMethod_None"
    end
    return exportRenditions(photos, destDir, settings, progress)
end

function Export.pixelSources(photos, destDir, progress)
    return Export.retouchSources(photos, destDir, "JPEG", progress)
end

function Export.copyFile(sourcePath, destPath)
    local source = io.open(sourcePath, "rb")
    if source == nil then
        error("Unable to open source file: " .. tostring(sourcePath))
    end
    local data = source:read("*all")
    source:close()

    local dest = io.open(destPath, "wb")
    if dest == nil then
        error("Unable to open destination file: " .. tostring(destPath))
    end
    dest:write(data)
    dest:close()
    return destPath
end

function Export.finalFiles(photos, destDir, format, progress)
    Export.ensureDir(destDir)
    local exportFormat = format or "JPEG"
    local settings = {
        LR_export_destinationType = "specificFolder",
        LR_export_destinationPathPrefix = destDir,
        LR_export_useSubfolder = false,
        LR_collisionHandling = "rename",
        LR_format = exportFormat,
        LR_jpeg_quality = 0.92,
        LR_export_colorSpace = "sRGB",
        LR_size_doConstrain = false,
        LR_outputSharpeningOn = true,
        LR_outputSharpeningMedia = "screen",
        LR_outputSharpeningLevel = 1,
    }

    if exportFormat == "TIFF" then
        settings.LR_tiff_bitDepth = 16
        settings.LR_tiff_compressionMethod = "compressionMethod_None"
    end

    return exportRenditions(photos, destDir, settings, progress)
end

return Export
