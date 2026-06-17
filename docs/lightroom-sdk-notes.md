# Lightroom SDK Notes

Implementation relies on stable Lightroom Classic plug-in surfaces:

- Lua plug-in metadata through `Info.lua`.
- Library menu entries through `LrLibraryMenuItems`.
- Selected-photo access through `LrApplication.activeCatalog():getTargetPhotos()`.
- Preview/proof/final rendering through `LrExportSession`.
- Local service calls through `LrHttp`.
- Non-destructive Develop changes through plug-in Develop presets and `photo:applyDevelopPreset(...)`.
- Plug-in-owned metadata through `photo:setPropertyForPlugin(...)`.

Adobe references:

- [Lightroom Classic SDK](https://developer.adobe.com/lightroom-classic/)
- [XMP and ACR sidecar files in Lightroom Classic](https://helpx.adobe.com/lightroom-classic/help/create-xmp-acr-files.html)

The MVP avoids directly editing `.lrcat`, RAW files, XMP files, ACR sidecars, or Lightroom mask internals.
