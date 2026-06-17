# Lightroom Parameter Map

The service emits product-level parameter names. The Lightroom plug-in receives `lightroom_settings` for direct preset creation.

| Product parameter | Lightroom Develop setting |
| --- | --- |
| `exposure` | `Exposure2012` |
| `contrast` | `Contrast2012` |
| `highlights` | `Highlights2012` |
| `shadows` | `Shadows2012` |
| `whites` | `Whites2012` |
| `blacks` | `Blacks2012` |
| `temperature` | `TemperatureDelta` |
| `tint` | `Tint` |
| `texture` | `Texture` |
| `clarity` | `Clarity2012` |
| `dehaze` | `Dehaze` |
| `vibrance` | `Vibrance` |
| `saturation` | `Saturation` |
| `sharpening` | `Sharpness` |
| `noise_reduction` | `LuminanceSmoothing` |

`TemperatureDelta` is not written directly to Lightroom. The plug-in reads the current Develop setting, adds the delta to the existing white balance temperature, sets `WhiteBalance = "Custom"`, and applies the resulting absolute `Temperature`.

`Tint` is also treated as an incremental correction by the plug-in.

## Safety Rules

Absolute parameters are clamped in `local-ai-service/app/lightroom_params.py`.

Review deltas are clamped separately and more tightly:

```text
exposure: +/-0.15 per review pass
temperature: +/-250 per review pass
highlights/shadows: +/-12 per review pass
vibrance: +/-6 per review pass
```

The Lightroom plug-in caps automatic review passes at 2.
