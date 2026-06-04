Option Explicit

Dim fso, shell, rootDir, nativeExe, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

rootDir = fso.GetParentFolderName(WScript.ScriptFullName)
nativeExe = fso.BuildPath(rootDir, "src-tauri\target\debug\dreamrender.exe")

If fso.FileExists(nativeExe) Then
  shell.CurrentDirectory = fso.GetParentFolderName(nativeExe)
  shell.Run Quote(nativeExe), 1, False
Else
  shell.CurrentDirectory = rootDir
  shell.Environment("PROCESS")("PYTHONPATH") = fso.BuildPath(rootDir, "src")
  command = shell.ExpandEnvironmentStrings("%COMSPEC%") & " /d /c pythonw.exe -m dreamrender app-v2"
  shell.Run command, 0, False
End If

Function Quote(value)
  Quote = """" & value & """"
End Function
