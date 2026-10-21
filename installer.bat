@echo off
REM ============================================================
REM  ImmoGest - installation automatique sous Windows
REM  Usage (PowerShell ou Invite de commandes, dans le dossier du projet) :
REM      .\installer.bat
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo === ImmoGest : installation ===

REM --- 1. Choix de Python (Django 5.1 : versions 3.10 a 3.13) ---
set "PY="
for %%V in (3.12 3.13 3.11 3.10) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1
        if not errorlevel 1 set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo.
    echo ERREUR : aucun Python 3.10 a 3.13 trouve.
    echo Installez Python 3.12 depuis https://www.python.org/downloads/
    echo ^(cochez "Add python.exe to PATH"^) puis relancez ce script.
    goto :fin_erreur
)
echo Python utilise : %PY%
%PY% --version

REM --- 2. Environnement virtuel dans ce dossier ---
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo Ancien environnement .venv incompatible : il est recree.
        rmdir /s /q ".venv"
    )
)
if not exist ".venv\Scripts\python.exe" (
    echo Creation de l'environnement virtuel .venv ...
    %PY% -m venv .venv
    if errorlevel 1 goto :fin_erreur
)

REM --- 3. Dependances (pip lance par le Python du .venv : aucune confusion possible) ---
echo.
echo === Installation des dependances (quelques minutes) ===
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 (
    echo.
    echo ERREUR pendant l'installation des dependances ^(voir le message ci-dessus^).
    goto :fin_erreur
)
".venv\Scripts\python.exe" -c "import django; print('Django', django.get_version(), 'installe')"
if errorlevel 1 goto :fin_erreur

REM --- 4. Configuration et base de donnees ---
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo Fichier .env cree a partir de .env.example
)
echo.
echo === Migration de la base de donnees ===
".venv\Scripts\python.exe" manage.py migrate
if errorlevel 1 goto :fin_erreur

echo.
echo ===========================================================
echo  Installation terminee.
echo  Lancer le site :  .\.venv\Scripts\python.exe manage.py runserver
echo  Puis ouvrir :     http://127.0.0.1:8000
echo  Donnees de demonstration (facultatif) :
echo                    .\.venv\Scripts\python.exe manage.py seed_demo
echo ===========================================================
pause
exit /b 0

:fin_erreur
echo.
echo L'installation a echoue. Copiez le message d'erreur ci-dessus pour obtenir de l'aide.
pause
exit /b 1
