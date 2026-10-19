# Real-Corpus Evaluation — Quick Scan vs Deep Scan

Generated 2026-10-19 00:01 by `scripts/real_corpus_eval.py`. Source folders were read-only; projects are stored with the `realeval_` prefix.

## 1. Corpus

| Project | Folder | Files | Code | Text | Chars | Ingest s | Embed s | Vectors (code/text) |
|---|---|---|---|---|---|---|---|---|
| `mizan_monorepo` | `D:\mizan_monorepo` | 522 | 469 | 53 | 7090796 | 56.4 | 948.8 | 469/53 |
| `3d_react_website` | `D:\3d-react-website` | 15 | 15 | 0 | 35423 | 0.4 | 31.6 | 15/0 |
| `accounting` | `D:\accounting` | 63 | 61 | 2 | 247089 | 2.6 | 122.8 | 61/2 |
| `ai_engine` | `D:\AI engine` | 187 | 134 | 53 | 2512660 | 27.0 | 436.4 | 134/53 |
| `ai_surveillance_system` | `D:\AI surveillance system` | 3 | 2 | 1 | 13122 | 0.1 | 5.0 | 2/1 |
| `application_of_tinyml` | `D:\application of TinyML` | 52 | 0 | 52 | 481388 | 3.8 | 223.2 | 0/52 |
| `c_accounting_app_mizan` | `D:\C# accounting app(Mizan)` | 36 | 36 | 0 | 34711 | 0.7 | 32.9 | 36/0 |
| `compressed` | `D:\Compressed` | 0 | 0 | 0 | 0 | - | - | -/- |
| `crystal_helix_erp` | `D:\crystal-helix-erp` | 475 | 471 | 4 | 2688651 | 28.1 | 666.9 | 471/4 |
| `cybersecurity_dip_proj` | `D:\CyberSecurity+DIP projects` | 48 | 26 | 22 | 5602541 | 38.3 | - | -/- |
| `encrypted_traffic_anal` | `D:\Encrypted Traffic analysis` | 11 | 6 | 5 | 45336 | 0.4 | - | -/- |
| `frontend` | `D:\frontend` | 46 | 46 | 0 | 270142 | 2.0 | - | -/- |
| `local_agent_ui_ready` | `D:\local-agent-ui-ready` | 31 | 26 | 5 | 139337 | 1.6 | - | -/- |
| `lordsmobilebot` | `D:\LordsMobileBot` | 9 | 6 | 3 | 129313 | 1.2 | - | -/- |
| `manus_like_agent` | `D:\manus-like agent` | 215 | 191 | 24 | 2671746 | 22.1 | - | -/- |

## 2. Quick Scan — max fusion score (%) per project pair

Rows = scanned project, columns = matched project. Blank = no match reported.

| ↓ scanned / matched → | `mizan_mono` | `3d_react_w` | `accounting` | `ai_engine` | `ai_surveil` | `applicatio` | `c_accounti` | `compressed` | `crystal_he` | `cybersecur` | `encrypted_` | `frontend` | `local_agen` | `lordsmobil` | `manus_like` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `mizan_monorepo` | — |  | 100 | 1 |  |  |  |  |  |  |  |  |  |  |  |
| `3d_react_website` |  | — |  |  |  |  |  |  |  |  |  |  |  |  |  |
| `accounting` | 100 |  | — |  |  |  |  |  |  |  |  |  |  |  |  |
| `ai_engine` | 1 |  |  | — |  |  |  |  | 10 |  |  |  |  |  |  |
| `ai_surveillance_system` |  |  |  |  | — |  |  |  |  |  |  |  |  |  |  |
| `application_of_tinyml` |  |  |  |  |  | — |  |  |  |  |  |  |  |  |  |
| `c_accounting_app_mizan` |  |  |  |  |  |  | — |  |  |  |  |  |  |  |  |
| `compressed` |  |  |  |  |  |  |  | — |  |  |  |  |  |  |  |
| `crystal_helix_erp` |  |  |  | 10 |  |  |  |  | — |  |  |  |  |  |  |
| `cybersecurity_dip_proj` |  |  |  |  |  |  |  |  |  | — |  |  |  |  |  |
| `encrypted_traffic_anal` |  |  |  |  |  |  |  |  |  |  | — |  |  |  |  |
| `frontend` |  |  |  |  |  |  |  |  |  |  |  | — |  |  |  |
| `local_agent_ui_ready` |  |  |  |  |  |  |  |  |  |  |  |  | — |  |  |
| `lordsmobilebot` |  |  |  |  |  |  |  |  |  |  |  |  |  | — |  |
| `manus_like_agent` |  |  |  |  |  |  |  |  |  |  |  |  |  |  | — |

## 3. Deep Scan — max calibrated semantic similarity (%) per project pair

Rows = scanned project, columns = matched project. Blank = no match reported.

| ↓ scanned / matched → | `mizan_mono` | `3d_react_w` | `accounting` | `ai_engine` | `ai_surveil` | `applicatio` | `c_accounti` | `compressed` | `crystal_he` | `cybersecur` | `encrypted_` | `frontend` | `local_agen` | `lordsmobil` | `manus_like` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `mizan_monorepo` | — | 75 | 100 | 70 |  | 46 | 90 |  | 77 |  |  |  |  |  |  |
| `3d_react_website` | 75 | — | 76 | 95 |  |  |  |  | 91 |  |  |  |  |  |  |
| `accounting` | 100 | 76 | — | 78 |  |  | 73 |  | 75 |  |  |  |  |  |  |
| `ai_engine` | 70 | 95 | 78 | — | 53 | 52 | 10 |  | 91 |  |  |  |  |  |  |
| `ai_surveillance_system` | 0 |  |  | 54 | — | 10 |  |  |  |  |  |  |  |  |  |
| `application_of_tinyml` | 46 |  | 41 | 52 |  | — |  |  |  |  |  |  |  |  |  |
| `c_accounting_app_mizan` | 90 |  | 73 | 58 |  |  | — |  | 74 |  |  |  |  |  |  |
| `compressed` |  |  |  |  |  |  |  | — |  |  |  |  |  |  |  |
| `crystal_helix_erp` | 77 | 91 | 75 | 91 | 41 |  | 74 |  | — |  |  |  |  |  |  |
| `cybersecurity_dip_proj` |  |  |  |  |  |  |  |  |  | — |  |  |  |  |  |
| `encrypted_traffic_anal` |  |  |  |  |  |  |  |  |  |  | — |  |  |  |  |
| `frontend` |  |  |  |  |  |  |  |  |  |  |  | — |  |  |  |
| `local_agent_ui_ready` |  |  |  |  |  |  |  |  |  |  |  |  | — |  |  |
| `lordsmobilebot` |  |  |  |  |  |  |  |  |  |  |  |  |  | — |  |
| `manus_like_agent` |  |  |  |  |  |  |  |  |  |  |  |  |  |  | — |

## 4. Per-project scan summary

| Project | Quick s | Quick verdict | Quick overall % | # comparisons | Deep s | # deep matches |
|---|---|---|---|---|---|---|
| `mizan_monorepo` | 717.0 | CRITICAL | 100.0 | 2663 | 2.72 | 2610 |
| `3d_react_website` | 2.1 | SAFE | 0.0 | 0 | 0.47 | 75 |
| `accounting` | 6.4 | CRITICAL | 100.0 | 8 | 1.09 | 315 |
| `ai_engine` | 772.9 | CRITICAL | 100.0 | 427 | 1.86 | 935 |
| `ai_surveillance_system` | 1.5 | CRITICAL | 98.38 | 4 | 0.27 | 15 |
| `application_of_tinyml` | 1.9 | SAFE | 0.0 | 0 | 0.25 | 260 |
| `c_accounting_app_mizan` | 1.9 | SAFE | 0.0 | 0 | 0.91 | 180 |
| `compressed` | - | Project 'realeval_compressed' not found in database. | - | - | - | - |
| `crystal_helix_erp` | 1786.8 | CRITICAL | 100.0 | 15553 | 2.82 | 2375 |
| `cybersecurity_dip_proj` | - | Project 'realeval_cybersecurity_dip_projects' not found in database. | - | - | - | - |
| `encrypted_traffic_anal` | - | Project 'realeval_encrypted_traffic_analysis' not found in database. | - | - | - | - |
| `frontend` | - | Project 'realeval_frontend' not found in database. | - | - | - | - |
| `local_agent_ui_ready` | - | Project 'realeval_local_agent_ui_ready' not found in database. | - | - | - | - |
| `lordsmobilebot` | - | Project 'realeval_lordsmobilebot' not found in database. | - | - | - | - |
| `manus_like_agent` | - | Project 'realeval_manus_like_agent' not found in database. | - | - | - | - |

## 5. Top 25 file-level matches (Quick Scan, by fusion score)

| Scanned project | File | Matched project | Matched file | Win % | Sem % | Fusion % | Contain % | Verdict |
|---|---|---|---|---|---|---|---|---|
| `mizan_monorepo` | `app_main\analyze_output.txt` | `orepo` | `app_main\analyze_output.txt` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\android\app\build.gradle.kts` | `orepo` | `app_main\apps\android\app\build.gradle.kts` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\android\app\src\main\kotlin\com\example\mizan\LocalAiNative.kt` | `orepo` | `app_main\apps\android\app\src\main\kotlin\com\example\mizan\LocalAiNative.kt` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\android\app\src\main\kotlin\com\example\mizan\MainActivity.kt` | `orepo` | `app_main\apps\android\app\src\main\kotlin\com\example\mizan\MainActivity.kt` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\android\build.gradle.kts` | `orepo` | `app_main\apps\android\build.gradle.kts` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\android\build.gradle.kts` | `accounting` | `apps\mizan\apps\mizan_app\android\build.gradle.kts` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\android\settings.gradle.kts` | `orepo` | `app_main\apps\android\settings.gradle.kts` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\android_build_log.txt` | `orepo` | `app_main\apps\android_build_log.txt` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\lib\main.dart` | `orepo` | `app_main\apps\lib\main.dart` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\lib\src\app_database_provider.dart` | `orepo` | `app_main\apps\lib\src\app_database_provider.dart` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\lib\src\app_localizations_provider.dart` | `orepo` | `app_main\apps\lib\src\app_localizations_provider.dart` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\test\widget_test.dart` | `orepo` | `app_main\apps\test\widget_test.dart` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\web\index.html` | `orepo` | `app_main\apps\web\index.html` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\web\sql-wasm.js` | `orepo` | `app_main\apps\web\sql-wasm.js` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\windows\runner\flutter_window.cpp` | `orepo` | `app_main\apps\windows\runner\flutter_window.cpp` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\windows\runner\flutter_window.h` | `orepo` | `app_main\apps\windows\runner\flutter_window.h` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\windows\runner\local_ai_windows.h` | `orepo` | `app_main\apps\windows\runner\local_ai_windows.h` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\windows\runner\main.cpp` | `orepo` | `app_main\apps\windows\runner\main.cpp` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\windows\runner\resource.h` | `orepo` | `app_main\apps\windows\runner\resource.h` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\windows\runner\utils.cpp` | `orepo` | `app_main\apps\windows\runner\utils.cpp` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\windows\runner\utils.h` | `orepo` | `app_main\apps\windows\runner\utils.h` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\windows\runner\win32_window.cpp` | `orepo` | `app_main\apps\windows\runner\win32_window.cpp` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\apps\windows\runner\win32_window.h` | `orepo` | `app_main\apps\windows\runner\win32_window.h` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\docs\ai-agent-architecture.md` | `orepo` | `app_main\docs\ai-agent-architecture.md` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
| `mizan_monorepo` | `app_main\docs\local-ai-tflite-bridge.md` | `orepo` | `app_main\docs\local-ai-tflite-bridge.md` | 100.0 | 100.0 | 100.0 | 100.0 | CRITICAL |
