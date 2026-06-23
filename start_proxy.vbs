Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "pythonw """ & Replace(WScript.ScriptFullName, "start_proxy.vbs", "proxy.py") & """", 0, False
