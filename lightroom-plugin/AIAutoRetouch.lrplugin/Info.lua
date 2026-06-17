return {
    LrSdkVersion = 14.0,
    LrSdkMinimumVersion = 7.0,
    LrToolkitIdentifier = "com.local.ai-lightroom-retouch",
    LrPluginName = "AI Auto Retouch",
    LrPluginInfoUrl = "https://developer.adobe.com/lightroom-classic/",

    LrInitPlugin = "Init.lua",
    LrMetadataProvider = "MetadataProvider.lua",

    LrLibraryMenuItems = {
        {
            title = "AI Auto Retouch...",
            file = "MenuAutoRetouch.lua",
        },
        {
            title = "AI Review Current Batch...",
            file = "MenuReview.lua",
        },
        {
            title = "AI Export...",
            file = "MenuExport.lua",
        },
        {
            title = "AI Settings...",
            file = "MenuSettings.lua",
        },
        {
            title = "AI Debug Status...",
            file = "MenuDebug.lua",
        },
    },

    VERSION = {
        major = 0,
        minor = 1,
        revision = 0,
        build = 1,
    },
}
