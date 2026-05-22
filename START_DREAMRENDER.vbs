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
  shell.Environment("PROCESS")("PATH") = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\.cargo\bin;" & shell.Environment("PROCESS")("PATH")
  command = shell.ExpandEnvironmentStrings("%COMSPEC%") & " /d /c npm run tauri:dev"
  shell.Run command, 0, False
End If

Function Quote(value)
  Quote = """" & value & """"
End Function
