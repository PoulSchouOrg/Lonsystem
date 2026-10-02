# Opsætning af produktionsmaskinen fra bar Windows 11

Denne guide antager: den bærbare (denne maskine) er udviklingsmaskinen, og den nye
maskine ved siden af er tom (kun Windows 11) og skal være produktionsserveren.
Alt køres i almindelig PowerShell/cmd — ingen venv, ligesom udviklingsmaskinen i dag.

## Del 1 – Én gang, på DENNE (bærbare) maskine

1. Opret en konto på github.com hvis du ikke har en, og opret et **privat** repo,
   fx `lonsystem`. Kopiér repoets URL (fx `https://github.com/PoulSchouOrg/Lonsystem.git`).
2. Kør i denne mappe:
   ```
   git remote add origin https://github.com/PoulSchouOrg/Lonsystem.git
   git push -u origin main
   ```
   Nu ligger koden centralt på GitHub. `.env` og databasen bliver IKKE sendt med
   (de står i `.gitignore`) — det er meningen.

## Del 2 – På den NYE (tomme) maskine

### 2.1 Installér Python
- Gå til python.org → Downloads → hent nyeste 3.13.x til Windows.
- Kør installeren. **Vigtigt:** sæt flueben i "Add python.exe to PATH" på første skærm.
- Verificér i PowerShell:
  ```
  python --version
  ```

### 2.2 Installér Git
- Gå til git-scm.com → Download for Windows.
- Kør installeren, tag standardvalgene hele vejen igennem.
- Verificér:
  ```
  git --version
  ```

### 2.3 Hent koden
```
cd C:\Users\LoenPC
git clone https://github.com/PoulSchouOrg/Lonsystem.git Lonsystem
cd C:\Users\LoenPC\Lonsystem
```
Placér den her — **ikke** i en OneDrive-mappe (se forklaring i tidligere svar:
OneDrive-synkronisering af en levende database er risikabelt). Undgå bevidst danske
bogstaver (æøå) i selve mappenavnet — det gav en tegnsæt-fejl i PowerShell tidligere.

### 2.4 Installér Python-pakkerne
```
cd C:\Users\LoenPC\Lonsystem\app
python -m pip install -r requirements.txt
```

### 2.5 Opret produktionens egen .env
```
copy .env.example .env
notepad .env
```
Udfyld:
- `SESSION_SECRET` — generér en ny unik værdi (kør på denne maskine):
  ```
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` — de rigtige
  driftsoplysninger til udsendelse af mails.
- Lad `ENTRA_*` stå tomme indtil SSO evt. tages i brug.

### 2.6 Testkør manuelt (før vi gør det til en service)
```
cd C:\Users\LoenPC\Lonsystem\app
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```
Åbn en browser på samme maskine: `http://localhost:8000`. Virker det, luk med Ctrl+C.

### 2.7 Åbn porten i firewallen (så kolleger kan tilgå den fra deres egne PC'er)
Kør i en PowerShell **som administrator**:
```
New-NetFirewallRule -DisplayName "Lonsystem" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```
Find maskinens lokale IP-adresse med `ipconfig` (feltet "IPv4-adresse"). Kolleger
tilgår herefter systemet på `http://<den-ip-adresse>:8000`. Overvej at bede jeres
netværksansvarlige om at reservere en fast IP til denne maskine i routeren, så
adressen ikke ændrer sig efter en genstart.

## Del 3 – Gør det til en vedvarende opgave (kører uden åbent vindue, starter ved boot)

Helt native Windows — ingen tredjeparts-software. [setup_scheduled_task.ps1](setup_scheduled_task.ps1)
finder selv den fulde sti til `python.exe` (mere robust end at stole på at `python`/`py`
er på PATH for SYSTEM-kontoen) og opretter serveren som en Task Scheduler-opgave, der
kører `python.exe` direkte — Task Scheduler genstarter den selv op til 999 gange
(1 minuts mellemrum) hvis processen nogensinde stopper uventet.

1. Åbn PowerShell i `C:\Users\LoenPC\Lonsystem` — scriptet tjekker selv om du er
   administrator, og hvis ikke, åbner det automatisk et nyt, forhøjet vindue (du skal
   bare acceptere UAC-prompten).
2. Kør opsætnings-scriptet:
   ```
   powershell -ExecutionPolicy Bypass -File deploy\setup_scheduled_task.ps1
   ```
   Det opretter FIRE opgaver: "Lonsystem" (selve serveren, starter ved boot, fjerner
   Windows' normale 3-dages køretidsgrænse så den ikke bliver slået ihjel om natten,
   genstarter automatisk ved crash), "LonsystemAutoDeploy" (tjekker GitHub hvert
   5. minut for evigt og henter ny kode, se Del 4), "LonsystemNightlyRestart"
   (genstarter serveren hver nat kl. 23:00 så den nye kode tages i brug, se Del 5),
   og "LonsystemBackup" (backup af database og satsfiler kl. 00:00/06:00/12:00/18:00,
   se Del 7). Scriptet kan køres igen når som helst — det opdaterer bare de
   eksisterende opgaver.
3. Tjek at den kører: `http://<ip-adresse>:8000` i en browser fra en anden PC.
4. Nyttige kommandoer fremover:
   ```
   Get-ScheduledTask -TaskName Lonsystem | Get-ScheduledTaskInfo   # status
   Stop-ScheduledTask -TaskName Lonsystem                           # stop
   Start-ScheduledTask -TaskName Lonsystem                          # (gen)start
   ```
   Serveren starter nu automatisk ved genstart af maskinen. Output/fejl fra kørslen
   ses i Task Scheduler (find opgaven → fanen "Historik"), eller ved midlertidigt selv
   at køre `python -m uvicorn main:app --host 0.0.0.0 --port 8000` fra `app`-mappen
   for at se live output i et almindeligt vindue.

## Del 3B – Uden admin-rettigheder: opret de fire opgaver manuelt via GUI'et

Har du ikke lokal admin-adgang (og kan ikke få en kollega til at køre scriptet),
kan du oprette de samme fire opgaver manuelt via Task Scheduler-GUI'et — de
kører så under din egen Windows-konto i stedet for SYSTEM, hvilket ikke kræver
admin. Ulempen: opgaverne kræver at der findes en gemt adgangskode til din
konto for at kunne køre uden at du er logget ind (Windows spørger om den ved
oprettelse) — spørg IT om det er acceptabelt hos jer, hvis maskinen skal kunne
genstarte uden nogen logger ind bagefter.

**Forberedelse — find Pythons fulde sti** (skal bruges i flere opgaver nedenfor):
```
py -c "import sys; print(sys.executable)"
```
Notér outputtet, fx `C:\Users\LoenPC\AppData\Local\Programs\Python\Python313\python.exe`.

**Sæt backup-mappen** (kræver ikke admin, da den sættes for din egen bruger):
```
[Environment]::SetEnvironmentVariable("LONSYSTEM_BACKUP_DIR", "C:\Users\LoenPC\OneDrive - Poul Schou A S\LonsystemBackup", "User")
```

**Åbn Task Scheduler:** Start-menuen → søg "Task Scheduler" → åbn den (kræver ikke
admin at åbne selve programmet). Højreklik "Task Scheduler Library" i venstre side
→ **"Create Task..."** (ikke "Create Basic Task" — vi skal bruge de ekstra faner).

For hver af de fire opgaver nedenfor: udfyld fanerne som beskrevet, og klik OK.
Windows beder om din adgangskode, fordi "Run whether user is logged on or not"
er valgt — indtast den, det er sådan opgaven kan køre uden at du er logget ind.

---

Nedenfor er hver fane beskrevet i fuld detalje for alle fire opgaver. Danske
menunavne er brugt (dit Windows er dansk); den engelske betegnelse står i
parentes første gang, hvis dit udseende skulle afvige lidt.

---

### Opgave 1 — "Lonsystem" (selve serveren)

**Generelt (General):**
- Navn: `Lonsystem`
- Under "Sikkerhedsindstillinger" (Security options): vælg **"Kør uanset om
  brugeren er logget på eller ej"** (Run whether user is logged on or not).

**Udløsere (Triggers):** Ny... → Start opgaven: **"Ved opstart"** (At startup).
Lad resten stå på standard, tryk OK.

**Handlinger (Actions):** Ny... →
- Handling: "Start et program" (Start a program) — er allerede valgt som standard.
- Program/script: indsæt den fulde Python-sti fra forberedelsen ovenfor.
- Tilføj argumenter (valgfrit): `-m uvicorn main:app --host 0.0.0.0 --port 8000`
- Start i (valgfrit): `C:\Users\LoenPC\Lonsystem\app`

**Betingelser (Conditions):**
- Under "Strøm" (Power): fjern fluebenet i **"Start kun opgaven, hvis computeren
  kører på lysnetstrøm"** (Start the task only if the computer is on AC power) —
  serveren skal køre uanset strømkilde. Fjern også fluebenet i **"Stop, hvis
  computeren skifter til batteridrift"**, hvis den findes.
- Lad "Netværk" stå urørt (ikke nødvendigt at afkrydse noget her).

**Indstillinger (Settings):**
- Behold flueben i **"Tillad, at opgaven køres efter behov"** (Allow task to be
  run on demand) — bruges når du selv trykker "Kør"/"Run" for at teste.
- Behold flueben i **"Kør opgaven så hurtigt som muligt efter en planlagt start
  er gået glip af"** (Run task as soon as possible after a scheduled start is
  missed).
- Sæt flueben i **"Hvis opgaven mislykkes, så genstart den hvert:"** (If the
  task fails, restart every) → `1 minut`, og **"Forsøg at genstarte op til:"**
  → det højeste tal du kan vælge/indtaste (fx `999`, ellers det maksimale
  preset, typisk mindst `3`).
- **Vigtigst af alt:** fjern fluebenet i **"Stop opgaven, hvis den kører længere
  end:"** (Stop the task if it runs longer than) — helt afkrydset væk, ikke bare
  sat til et stort tal. Lader du den stå til (standard er 3 dage), slår Windows
  serveren ihjel midt om natten uden varsel.
- "Hvis opgaven allerede kører, gælder følgende regel:" → vælg **"Start ikke en
  ny forekomst"** (Do not start a new instance).

---

### Opgave 2 — "LonsystemAutoDeploy" (henter ny kode hvert 5. minut, genstarter ikke)

**Generelt:** Navn: `LonsystemAutoDeploy`. "Kør uanset om brugeren er logget på
eller ej".

**Udløsere:** Ny... → Start opgaven: **"På en tidsplan"** (On a schedule) →
Indstillinger: **"Daglig"** (Daily), starttidspunkt kan være hvad som helst (fx
nu). Sæt flueben i **"Gentag opgaven hver:"** (Repeat task every) → skriv/vælg
`5 minutter`, og sæt feltet **"i en varighed af:"** (for a duration of) til
**"I det uendelige"** (Indefinitely).

**Handlinger:** Ny... →
- Program/script: `powershell.exe`
- Tilføj argumenter: `-NoProfile -ExecutionPolicy Bypass -File "C:\Users\LoenPC\Lonsystem\deploy\auto_deploy_check.ps1"`
- Start i: `C:\Users\LoenPC\Lonsystem`

**Betingelser:** Samme som Opgave 1 — fjern fluebenene under "Strøm", så tjekket
kører uanset strømkilde.

**Indstillinger:**
- Behold "Tillad, at opgaven køres efter behov" og "Kør så hurtigt som muligt
  efter en gået-glip-af start".
- Sæt flueben i **"Stop opgaven, hvis den kører længere end:"** → `5 minutter`
  (i modsætning til Opgave 1 vil vi HER gerne have en grænse — den skal være
  hurtigt overstået, og en fastlåst kørsel skal ikke blokere for de næste).
- "Hvis opgaven allerede kører" → **"Start ikke en ny forekomst"** (vigtigt,
  ellers kan flere tjek køre oven i hinanden).

---

### Opgave 3 — "LonsystemNightlyRestart" (genstart kl. 23:00)

**Generelt:** Navn: `LonsystemNightlyRestart`. "Kør uanset om brugeren er logget
på eller ej".

**Udløsere:** Ny... → "På en tidsplan" → "Daglig", klokkeslæt: `23:00`.

**Handlinger:** Ny... →
- Program/script: `powershell.exe`
- Tilføj argumenter: `-NoProfile -ExecutionPolicy Bypass -File "C:\Users\LoenPC\Lonsystem\deploy\restart_server.ps1"`
- Start i: `C:\Users\LoenPC\Lonsystem`

**Betingelser:** Fjern fluebenene under "Strøm", som ved de andre.

**Indstillinger:**
- Behold "Tillad, at opgaven køres efter behov" og "Kør så hurtigt som muligt
  efter en gået-glip-af start" (praktisk hvis maskinen fx var slukket kl. 23:00).
- Sæt "Stop opgaven, hvis den kører længere end:" → `5 minutter` (ren
  sikkerhedsgrænse, en genstart bør tage sekunder).
- "Hvis opgaven allerede kører" → "Start ikke en ny forekomst".

---

### Opgave 4 — "LonsystemBackup" (backup 4 gange dagligt)

**Generelt:** Navn: `LonsystemBackup`. "Kør uanset om brugeren er logget på
eller ej".

**Udløsere:** Opret FIRE separate udløsere (tryk Ny... fire gange) — én for
hvert klokkeslæt: "Daglig" kl. `00:00`, `06:00`, `12:00` og `18:00`.

**Handlinger:** Ny... →
- Program/script: indsæt den fulde Python-sti fra forberedelsen.
- Tilføj argumenter: `"C:\Users\LoenPC\Lonsystem\backup\backup.py"`
- Start i: `C:\Users\LoenPC\Lonsystem\backup`

**Betingelser:** Fjern fluebenene under "Strøm", som ved de andre.

**Indstillinger:**
- Behold "Tillad, at opgaven køres efter behov" og "Kør så hurtigt som muligt
  efter en gået-glip-af start".
- Sæt flueben i **"Stop opgaven, hvis den kører længere end:"** → `10 minutter`
  — denne MÅ gerne have en grænse, i modsætning til Opgave 1, da backup skal
  være hurtigt overstået.
- "Hvis opgaven allerede kører" → "Start ikke en ny forekomst".

---

Test hver opgave med det samme via højreklik → **"Run"** i Task Scheduler, og tjek
resultatet under fanen **"History"** for opgaven (hvis History er slået fra, aktivér
den via "Enable All Tasks History" i højre side).

Får du senere adgang til admin-rettigheder, kan I skifte til den mere robuste
SYSTEM-baserede opsætning ved blot at køre `setup_scheduled_task.ps1` som
administrator — den opdaterer/overskriver disse opgaver med `-Force`.

## Del 4 – Automatisk hentning af ny kode ved push til GitHub (uden genstart)

Opgaven "LonsystemAutoDeploy" (oprettet i Del 3) kører [auto_deploy_check.ps1](auto_deploy_check.ps1)
hvert 5. minut: den henter status fra GitHub, og hvis der er nye commits på `main`
siden sidst, kører den [pull_update.ps1](pull_update.ps1) (backup, ny kode, nye
Python-pakker). Er der intet nyt, gør den ingenting.

**Vigtigt:** den koerende server genstartes IKKE af dette tjek — den bliver ved med
at koere med den gamle kode i hukommelsen, uden afbrydelse for brugerne midt på
dagen. Den nye kode tages først reelt i brug ved næste genstart, som sker automatisk
hver nat kl. 23:00 (se Del 5), eller når du selv kører `restart_server.ps1`.

Se status for seneste kørsel:
```
Get-ScheduledTask -TaskName LonsystemAutoDeploy | Get-ScheduledTaskInfo
```

Hver kørsel logges desuden med tidsstempel i `deploy\auto_deploy.log` (i repo-mappen),
fx:
```
2026-08-27 19:50:02 - Tjek om der er aendringer
2026-08-27 19:50:03 - Ingen aendringer
2026-08-27 19:55:02 - Tjek om der er aendringer
2026-08-27 19:55:03 - Aendringer fundet til Lonsystem (a1b2c3d -> e4f5g6h)
2026-08-27 19:55:03 - Starter git pull (ingen genstart - sker kl. 23:00)
2026-08-27 19:55:05 - Succes - kode opdateret til e4f5g6h, venter paa genstart kl. 23:00
```
Åbn filen i notepad når som helst for at se historikken:
```
notepad C:\Users\LoenPC\Lonsystem\deploy\auto_deploy.log
```

## Del 5 – Nattelig genstart kl. 23:00

Opgaven "LonsystemNightlyRestart" (oprettet i Del 3) kører [restart_server.ps1](restart_server.ps1)
hver nat kl. 23:00: stopper og genstarter "Lonsystem"-opgaven, så al kode hentet
i løbet af dagen af auto-deploy'et rent faktisk bliver taget i brug. Kør den
manuelt når som helst for en øjeblikkelig genstart:
```
powershell -ExecutionPolicy Bypass -File deploy\restart_server.ps1
```

Efter genstart tjekker scriptet automatisk `http://localhost:8000/health` (op til
6 forsøg med 5 sekunders mellemrum). Svarer serveren korrekt, gemmes den
kørende commit i `deploy/last_known_good.txt`. Svarer den IKKE, ruller scriptet
automatisk tilbage til den sidst bekræftede version og genstarter igen — så en
fejlbehæftet commit fra det automatiske 5-minutters-tjek ikke kan slå produktionen
ned uden varsel til næste morgen. Alt logges til `deploy/restart.log` (Task
Scheduler-opgaven har ingen konsol, så uden denne logfil ville en fejl forsvinde
usynligt, ligesom `backup.py` gjorde før den blev rettet).

## Del 6 – (Valgfrit) Øjeblikkeligt fuldt deploy fra den bærbare, uden at vente til 23:00

1. På produktionsmaskinen: Indstillinger → Apps → Valgfrie funktioner → Tilføj en
   funktion → søg "OpenSSH Server" → Installer.
2. Start tjenesten og sæt den til autostart (PowerShell som administrator):
   ```
   Start-Service sshd
   Set-Service -Name sshd -StartupType Automatic
   New-NetFirewallRule -DisplayName "OpenSSH Server" -Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow
   ```
3. Fra den bærbare kan du nu, når du har testet en ændring og pushet den til
   `main` på GitHub, køre:
   ```
   ssh <bruger>@<produktions-ip> "cd C:\Users\LoenPC\Lonsystem; powershell -File deploy\deploy.ps1"
   ```
   I modsætning til det automatiske 5-minutters-tjek genstarter [deploy.ps1](deploy.ps1)
   serveren MED DET SAMME (den kalder `pull_update.ps1` og `restart_server.ps1` efter
   hinanden) — brug den når en rettelse ikke kan vente til den natlige genstart.

## Del 7 – Backup

Opgaven "LonsystemBackup" (oprettet i Del 3) kører [backup/backup.py](../backup/backup.py)
fire gange dagligt (00:00, 06:00, 12:00, 18:00) og zipper databasen samt de tre
Excel-satsfiler. Zip-filerne gemmes i:
```
C:\Users\LoenPC\OneDrive - Poul Schou A S\LonsystemBackup
```
(Oprindeligt blev "Dokumenter"-mappen brugt, men den mappe sad fast som en
ikke-skrivbar OneDrive-pladsholder fra 2026-09-01 og fremad — sqlite fejlede
med "unable to open database file" ved hvert forsøg. En ny mappe oprettet
direkte i OneDrive-roden virker uden problemer. Ret `LONSYSTEM_BACKUP_DIR`
(Del 3B) hvis stien nogensinde skal ændres igen.)

De seneste 5 dages backups beholdes, ældre slettes automatisk. Backup kører også
automatisk som første skridt i hvert deploy (både manuelt og via auto-deploy).

**Vigtigt:** at filen ligger i en OneDrive-mappe betyder ikke automatisk at den er
uploadet til skyen — selve OneDrive-synkroniseringen kræver at OneDrive-klienten
kører under en logget-ind brugers session. Kører produktionsmaskinen uden nogen
nogensinde logget ind, ligger backuppen kun lokalt indtil nogen logger ind. Tal med
IT om automatisk login til en dedikeret konto er acceptabelt hos jer, hvis
uploaden skal ske uden manuel indblanding.

Test manuelt:
```
Start-ScheduledTask -TaskName LonsystemBackup
Get-ScheduledTask -TaskName LonsystemBackup | Get-ScheduledTaskInfo
```

## Opsummeret arbejdsgang fremover
1. Udvikl og test på den bærbare (`--reload`, port 8000).
2. `git push` til `main` på GitHub når det er testet.
3. Inden for 5 minutter henter produktionsmaskinen automatisk den nye kode ned
   (uden at genstarte) — den bliver taget i brug ved den natlige genstart kl. 23:00.
4. Haster det, kør `deploy.ps1` mod produktionsmaskinen (lokalt eller via ssh, Del 6)
   for et øjeblikkeligt fuldt deploy med det samme.
