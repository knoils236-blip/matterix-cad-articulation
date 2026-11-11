@echo off
rem Build MatterixSwExporterSetup.exe on a Windows PC with SolidWorks installed. No other install needed:
rem uses the C# compiler shipped with Windows (.NET Framework 4.x) and the SolidWorks interop DLLs.
rem Optional argument: folder holding SolidWorks.Interop.*.dll if SolidWorks is not in the default place.
setlocal
cd /d "%~dp0"
set CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
set SW=%ProgramFiles%\SOLIDWORKS Corp\SOLIDWORKS\api\redist
if not "%~1"=="" set SW=%~1
if not exist "%CSC%" (echo .NET Framework 4 compiler not found: %CSC% & goto fail)
if not exist "%SW%\SolidWorks.Interop.sldworks.dll" (echo SolidWorks interop DLLs not found in: %SW% & echo Pass the folder as argument: build.bat "D:\...\SOLIDWORKS\api\redist" & goto fail)
if not exist dist mkdir dist
rem /link embeds the interop types, so the add-in DLL has no extra runtime dependency.
"%CSC%" /nologo /target:library /platform:x64 /optimize+ /out:dist\MatterixSwExporter.dll /link:"%SW%\SolidWorks.Interop.sldworks.dll" /link:"%SW%\SolidWorks.Interop.swconst.dll" /link:"%SW%\SolidWorks.Interop.swpublished.dll" /r:System.Windows.Forms.dll src\Addin.cs src\Exporter.cs
if errorlevel 1 goto fail
"%CSC%" /nologo /target:winexe /platform:x64 /optimize+ /out:dist\MatterixSwExporterSetup.exe /win32manifest:src\setup.manifest /resource:dist\MatterixSwExporter.dll,MatterixSwExporter.dll /r:System.Windows.Forms.dll src\Setup.cs
if errorlevel 1 goto fail
echo.
echo Built dist\MatterixSwExporterSetup.exe - close SolidWorks, then double-click it to install the add-in.
pause
exit /b 0
:fail
echo BUILD FAILED
pause
exit /b 1
