# Testmiljø

Et testmiljø ved siden af produktionen på LoenPC, til at prøve ændringer på rigtige data **før** de kommer i produktion.

| | Produktion | Testmiljø |
|---|---|---|
| Mappe | (som i dag) | `C:\LonsystemTest` |
| Kode | branch `main` | branch `staging` |
| Adresse | `http://<LoenPC>:8000` | `http://127.0.0.1:8100` (kun på LoenPC) |
| Data | den rigtige database | kopi af **nyeste backup-zip** |
| E-mail | ja | **aldrig** |
| Markering | – | rød **TESTMILJØ**-bjælke |

## Første gang
```powershell
powershell -ExecutionPolicy Bypass -File deploy\testmiljo\opsaet_testmiljo.ps1
powershell -ExecutionPolicy Bypass -File C:\LonsystemTest\deploy\testmiljo\opdater_testdata.ps1
powershell -ExecutionPolicy Bypass -File C:\LonsystemTest\deploy\testmiljo\planlaeg_natlig_opdatering.ps1   # valgfrit
```

## Til daglig
- Start: `C:\LonsystemTest\deploy\testmiljo\start_testmiljo.ps1` → åbn `http://127.0.0.1:8100`.
- Friske data: `opdater_testdata.ps1` (eller automatisk om natten). Alt man har ændret i testmiljøet forsvinder.
- Log: `C:\LonsystemTest\testmiljo.log`. Den advarer, hvis nyeste backup er over 36 timer gammel.

## Arbejdsgang
Ændring på egen branch → PR ind i `staging` → test her → PR `staging` → `main` (= udgivelse).

## Fjern testmiljøet
Stop testserveren, `Unregister-ScheduledTask -TaskName LonsystemTestdata -Confirm:$false`, slet `C:\LonsystemTest`
(den indeholder en kopi af lønsdata).
