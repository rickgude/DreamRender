!macro DREAMRENDER_STOP_PROCESS ProcessName
  nsExec::ExecToLog 'taskkill /IM "${ProcessName}" /F /T'
!macroend

!macro DREAMRENDER_STOP_RUNNING_APP
  !insertmacro DREAMRENDER_STOP_PROCESS "dreamrender-backend.exe"
  !insertmacro DREAMRENDER_STOP_PROCESS "dreamrender.exe"
  Sleep 750
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro DREAMRENDER_STOP_RUNNING_APP
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro DREAMRENDER_STOP_RUNNING_APP
!macroend
