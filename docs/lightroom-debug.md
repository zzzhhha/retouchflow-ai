# Lightroom Debug Mode

The Lightroom plug-in has a debug mode for diagnosing batch failures and local
service response issues.

## Enable

In Lightroom:

```text
Library > Plug-in Extras > AI Settings...
```

Enable:

```text
Debug > 开启调试日志和实时步骤状态
```

## Live Status

While a job is running, the Lightroom progress dialog now shows numbered steps,
for example:

```text
1/7 Export previews
2/7 Analyze previews
5/7 Review proof
2.2 Pixel retouch 3/12
```

You can also open:

```text
Library > Plug-in Extras > AI Debug Status...
```

It shows:

- current workflow
- current batch id
- current step
- current error detail
- debug log path
- recent debug log lines

## Log Files

Debug files are written under the system temp directory:

```text
%TEMP%/ai-lightroom-retouch/debug/debug.log
%TEMP%/ai-lightroom-retouch/debug/last-status.json
```

## JSON Response Errors

If the local service returns non-JSON content, Lightroom now reports:

- HTTP method
- URL
- JSON decode error
- first part of the raw response
- likely causes

This replaces low-level errors such as:

```text
[string "Json.lua"]:144: Invalid JSON number at position 1
```

Common causes:

- local FastAPI service is not running
- service URL is wrong
- endpoint path is wrong
- server returned a 500 error
- request payload caused validation or processing failure
