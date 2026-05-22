Option Explicit

Dim fso, shell, scriptDir, rootDir, launcher
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
rootDir = fso.GetParentFolderName(scriptDir)
launcher = fso.BuildPath(rootDir, "START_DREAMRENDER.vbs")

If Not fso.FileExists(launcher) Then
  MsgBox "DreamRender launcher was not found:" & vbCrLf & launcher, vbExclamation, "DreamRender"
  WScript.Quit 1
End If

shell.CurrentDirectory = rootDir
shell.Run """" & launcher & """", 1, False
