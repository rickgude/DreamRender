Option Explicit

Dim fso, shell, scriptDir, rootDir, pythonExe, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
rootDir = fso.GetParentFolderName(scriptDir)
pythonExe = FindPython(rootDir)

If pythonExe = "" Then
  MsgBox "DreamRender could not find regular Python 3.10+." & vbCrLf & vbCrLf & _
         "Install Python from python.org and enable 'Add python.exe to PATH'.", _
         vbExclamation, "DreamRender"
  WScript.Quit 1
End If

shell.Environment("PROCESS")("PYTHONPATH") = rootDir & "\src"
shell.CurrentDirectory = rootDir
command = Quote(pythonExe) & " -m dreamrender app"
shell.Run command, 0, False

Function FindPython(rootPath)
  Dim candidates, candidate, fromPath
  candidates = Array( _
    rootPath & "\.venv\Scripts\pythonw.exe", _
    rootPath & "\.venv\Scripts\python.exe", _
    "C:\Python314\pythonw.exe", _
    "C:\Python314\python.exe" _
  )

  For Each candidate In candidates
    If fso.FileExists(candidate) Then
      FindPython = candidate
      Exit Function
    End If
  Next

  fromPath = FindOnPath("pythonw.exe")
  If fromPath <> "" Then
    FindPython = fromPath
    Exit Function
  End If

  fromPath = FindOnPath("python.exe")
  If fromPath <> "" Then
    FindPython = fromPath
    Exit Function
  End If

  FindPython = ""
End Function

Function FindOnPath(exeName)
  Dim exec, line, lowerLine
  On Error Resume Next
  Set exec = shell.Exec(shell.ExpandEnvironmentStrings("%COMSPEC%") & " /d /c where " & exeName)
  If Err.Number <> 0 Then
    Err.Clear
    FindOnPath = ""
    Exit Function
  End If
  On Error GoTo 0

  Do Until exec.StdOut.AtEndOfStream
    line = Trim(exec.StdOut.ReadLine())
    lowerLine = LCase(line)
    If line <> "" And InStr(lowerLine, "\microsoft\windowsapps\") = 0 Then
      FindOnPath = line
      Exit Function
    End If
  Loop

  FindOnPath = ""
End Function

Function Quote(value)
  Quote = """" & value & """"
End Function
