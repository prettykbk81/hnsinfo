Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "python """ & Replace(WScript.ScriptFullName, "start_proxy.vbs", "proxy.py") & """", 0, False
