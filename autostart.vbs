' OpenJarvis silent autostart launcher
' Runs start-jarvis.sh via Git Bash without showing a console window
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """C:\Program Files\Git\bin\bash.exe"" -c ""cd /c/Users/taner/Desktop/OpenJarvis && ./start-jarvis.sh >> autostart.log 2>&1""", 0, False
