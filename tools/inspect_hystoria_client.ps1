# inspect_hystoria_client.ps1
# -----------------------------------------------------------------
# Dumps useful info about the Hystoria V5 client into
# logs/client_inspection.txt so we can reverse-engineer the protocol
# without needing interactive file browsing.
# -----------------------------------------------------------------

param(
    [string]$ClientPath = "C:\Users\touki\Desktop\Client Hystoria V5"
)

$ErrorActionPreference = "Continue"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir   = Join-Path $repoRoot "logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$output = Join-Path $logDir "client_inspection.txt"

# Reset the output file.
"" | Out-File -FilePath $output -Encoding UTF8

function Write-Section {
    param([string]$title)
    Add-Content -Path $output -Value ""
    Add-Content -Path $output -Value "============================================================"
    Add-Content -Path $output -Value "  $title"
    Add-Content -Path $output -Value "============================================================"
}

function Write-Line {
    param([string]$text)
    Add-Content -Path $output -Value $text
}

function Dump-FileContent {
    param([string]$label, [string]$path)
    Write-Section $label
    if (Test-Path $path) {
        try {
            $content = Get-Content -Path $path -Raw -ErrorAction Stop
            if ($content.Length -gt 8000) {
                Write-Line ($content.Substring(0, 8000))
                Write-Line ""
                Write-Line "[... tronque a 8000 caracteres ...]"
            } else {
                Write-Line $content
            }
        } catch {
            Write-Line "[ERREUR] Impossible de lire: $_"
        }
    } else {
        Write-Line "(fichier absent)"
    }
}

function Dump-Tree {
    param([string]$root, [int]$maxDepth = 3)
    if (-not (Test-Path $root)) {
        Write-Line "(chemin absent)"
        return
    }
    try {
        Get-ChildItem $root -Recurse -Depth $maxDepth -Force -ErrorAction SilentlyContinue |
            ForEach-Object {
                $rel = $_.FullName.Substring($ClientPath.Length)
                if ($_.PSIsContainer) {
                    Write-Line "[DIR]            $rel"
                } else {
                    Write-Line ("{0,12} {1}" -f $_.Length, $rel)
                }
            }
    } catch {
        Write-Line "Erreur arborescence: $_"
    }
}

Write-Section "Hystoria V5 client inspection"
Write-Line ("Genere le : " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-Line ("Chemin client : " + $ClientPath)

if (-not (Test-Path $ClientPath)) {
    Write-Line ""
    Write-Line "[ERREUR] Le dossier client n'existe pas a ce chemin."
    Write-Line "Verifie que l'archive Client Hystoria V5 a bien ete decompressee dans Downloads."
    Write-Host ""
    Write-Host "ERREUR: Dossier client introuvable a $ClientPath" -ForegroundColor Red
    Write-Host "Rapport partiel ecrit dans : $output"
    exit 1
}

# === 1. Top-level listing ===
Write-Section "Contenu racine du client"
try {
    Get-ChildItem $ClientPath -Force -ErrorAction SilentlyContinue |
        ForEach-Object {
            if ($_.PSIsContainer) {
                Write-Line ("[DIR]            " + $_.Name)
            } else {
                Write-Line ("{0,12} {1}" -f $_.Length, $_.Name)
            }
        }
} catch {
    Write-Line "Erreur: $_"
}

# === 2. Config files content ===
Dump-FileContent "zaap.yml" (Join-Path $ClientPath "zaap.yml")
Dump-FileContent ".release.infos.json" (Join-Path $ClientPath ".release.infos.json")
Dump-FileContent "manifest.json" (Join-Path $ClientPath "manifest.json")

# === 2b. Small text files at root that may contain session/auth data ===
Dump-FileContent "login.txt" (Join-Path $ClientPath "login.txt")
Dump-FileContent "session.txt" (Join-Path $ClientPath "session.txt")
Dump-FileContent "ticket.txt" (Join-Path $ClientPath "ticket.txt")
Dump-FileContent "main (no extension)" (Join-Path $ClientPath "main")

# === 3. resources/ tree (depth 3) ===
Write-Section "Arborescence resources/ (profondeur 3)"
Dump-Tree (Join-Path $ClientPath "resources") 3

# === 4. retroclient/ dedicated dump (full) ===
Write-Section "resources/app/retroclient/ (recursif complet)"
$retro = Join-Path $ClientPath "resources\app\retroclient"
if (Test-Path $retro) {
    Write-Line "TROUVE - contient probablement le vrai client Dofus 1.29"
    Write-Line ""
    Dump-Tree $retro 10
} else {
    Write-Line "(absent - c'est peut-etre seulement dans la version legacy 32 bits)"
}

# === 5. Search for Hystoria IP/port/domain in text files ===
Write-Section "Recherche '162.19.127.155', ':5555', 'hystoria' dans les fichiers texte"
try {
    $textFiles = Get-ChildItem $ClientPath -Recurse -Force -ErrorAction SilentlyContinue `
        -Include *.xml,*.json,*.yml,*.yaml,*.txt,*.js,*.conf,*.cfg,*.ini,*.html,*.htm,*.as,*.lua
    $found = $false
    foreach ($f in $textFiles) {
        try {
            $matches = Select-String -Path $f.FullName `
                -Pattern "162\.19\.127\.155|:5555|hystoria|gameserver|play-hystoria" `
                -ErrorAction SilentlyContinue
            if ($matches) {
                $found = $true
                $rel = $f.FullName.Substring($ClientPath.Length)
                Write-Line ""
                Write-Line "--- $rel ---"
                foreach ($m in $matches) {
                    $line = $m.Line.Trim()
                    if ($line.Length -gt 200) { $line = $line.Substring(0, 200) + "..." }
                    Write-Line ("  L{0}: {1}" -f $m.LineNumber, $line)
                }
            }
        } catch { }
    }
    if (-not $found) {
        Write-Line "(aucun match dans les fichiers texte - probablement dans app.asar ou .swf binaires)"
    }
} catch {
    Write-Line "Erreur de recherche: $_"
}

# === 6. app.asar detection ===
Write-Section "app.asar (archive Electron contenant le code JS du client)"
try {
    $asar = Get-ChildItem $ClientPath -Recurse -Filter "app.asar" -Force -ErrorAction SilentlyContinue
    if ($asar) {
        foreach ($a in $asar) {
            $rel = $a.FullName.Substring($ClientPath.Length)
            $sizeMb = [math]::Round($a.Length / 1MB, 2)
            Write-Line ("TROUVE: {0} ({1} MB)" -f $rel, $sizeMb)
        }
        Write-Line ""
        Write-Line "Ce fichier contient TOUT le code JS de l'application Electron."
        Write-Line "Pour l'extraire et le lire :"
        Write-Line "  1. Installer Node.js (nodejs.org)"
        Write-Line "  2. Dans PowerShell : npm install -g @electron/asar"
        Write-Line "  3. npx @electron/asar extract <chemin-app.asar> .\app_extracted\"
    } else {
        Write-Line "(pas de app.asar trouve)"
    }
} catch {
    Write-Line "Erreur: $_"
}

# === 7. SWF files (old Dofus 1.29 Flash assets) ===
Write-Section "Fichiers .swf (client Flash Dofus 1.29)"
try {
    $swfs = Get-ChildItem $ClientPath -Recurse -Filter "*.swf" -Force -ErrorAction SilentlyContinue
    if ($swfs) {
        foreach ($s in $swfs) {
            $rel = $s.FullName.Substring($ClientPath.Length)
            $sizeKb = [math]::Round($s.Length / 1KB, 1)
            Write-Line ("{0,10} KB  {1}" -f $sizeKb, $rel)
        }
    } else {
        Write-Line "(pas de .swf trouve au niveau racine)"
    }
} catch {
    Write-Line "Erreur: $_"
}

# === 8a. Crypto / CRYPTS / Shield keyword search in JS source files ===
Write-Section "Recherche mots-cles CRYPTO/CRYPTS/shield dans les .js (hors node_modules)"
try {
    $jsFiles = Get-ChildItem $ClientPath -Recurse -Force -ErrorAction SilentlyContinue `
        -Include *.js |
        Where-Object { $_.FullName -notmatch '\\node_modules\\' }
    $patterns = @(
        'CRYPTS',
        'cryptBasic',
        'parseBasicCrypted',
        'applyPacketToSendPostProcessing',
        'shield',
        'getRandomNetworkKey',
        'PacketEncryptor',
        'createCipher',
        'createDecipher'
    )
    $foundAny = $false
    foreach ($f in $jsFiles) {
        try {
            $rel = $f.FullName.Substring($ClientPath.Length)
            $hits = @()
            foreach ($p in $patterns) {
                $m = Select-String -Path $f.FullName -Pattern $p -SimpleMatch -ErrorAction SilentlyContinue
                if ($m) { $hits += $p }
            }
            if ($hits.Count -gt 0) {
                $foundAny = $true
                $sizeKb = [math]::Round($f.Length / 1KB, 1)
                Write-Line ("{0,10} KB  {1}    [matches: {2}]" -f $sizeKb, $rel, ($hits -join ', '))
            }
        } catch { }
    }
    if (-not $foundAny) {
        Write-Line "(aucun match - le code est probablement dans un .jsc bytecode)"
    }
} catch {
    Write-Line "Erreur recherche crypto: $_"
}

# === 8b. List all .jsc files (V8 bytecode where Shield/CRYPTS likely lives) ===
Write-Section "Fichiers .jsc (bytecode V8 - cibles potentielles pour CRYPTS)"
try {
    $jscFiles = Get-ChildItem $ClientPath -Recurse -Filter "*.jsc" -Force -ErrorAction SilentlyContinue
    if ($jscFiles) {
        foreach ($f in $jscFiles) {
            $rel = $f.FullName.Substring($ClientPath.Length)
            $sizeKb = [math]::Round($f.Length / 1KB, 1)
            Write-Line ("{0,10} KB  {1}" -f $sizeKb, $rel)
        }
    } else {
        Write-Line "(aucun .jsc trouve)"
    }
} catch {
    Write-Line "Erreur: $_"
}

# === 8c. List all .js files at app/ root level (hors node_modules), with size ===
Write-Section "Tous les .js du client (hors node_modules) avec taille"
try {
    $jsAll = Get-ChildItem $ClientPath -Recurse -Force -ErrorAction SilentlyContinue -Include *.js |
        Where-Object { $_.FullName -notmatch '\\node_modules\\' } |
        Sort-Object Length -Descending
    foreach ($f in $jsAll) {
        $rel = $f.FullName.Substring($ClientPath.Length)
        $sizeKb = [math]::Round($f.Length / 1KB, 1)
        Write-Line ("{0,10} KB  {1}" -f $sizeKb, $rel)
    }
    if (-not $jsAll) {
        Write-Line "(aucun .js trouve hors node_modules)"
    }
} catch {
    Write-Line "Erreur: $_"
}

# === 8d. package.json content (entry point, dependencies) ===
Dump-FileContent "resources/app/package.json" (Join-Path $ClientPath "resources\app\package.json")

# === 8e. netstat on port 5555 ===
Write-Section "Connexions TCP actuelles sur port 5555"
$ns = netstat -n | Select-String ":5555"
if ($ns) {
    foreach ($line in $ns) {
        Write-Line $line.Line.Trim()
    }
} else {
    Write-Line "(aucune - lance Dofus Retro.exe et reste a l'ecran de selection perso)"
}

# === Done ===
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Inspection terminee !" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Rapport ecrit dans :"
Write-Host "  $output" -ForegroundColor Cyan
Write-Host ""
Write-Host "Prochaine etape :"
Write-Host "  1. Ouvre ce fichier avec le Bloc-notes"
Write-Host "  2. Copie tout son contenu (Ctrl+A, Ctrl+C)"
Write-Host "  3. Colle-le dans le chat Claude"
Write-Host ""
