אני רוצה להבין משהו המנטור אמר שסופו של דבר האייג'נט הזה צריך להתחיל בקבלת מסמך שאומר מה האפלקציה שהוא בודק עכשיו זאת אומרת מה נכשב שבור ומה נחשב יציב בעייני עם נגיד אנחנו מדברים על עומס אז ךהסביר לאייג'נט של לחץ של 1000 בקשות זה הגבוולות שהמערכת צריכה לעמוד בו ושהוא יבין את זה ולא יריץ מבחן של 1000000 בקשות איפה זה קורה בארכיטקטורה שלנו?

# AI Project - Chaos Agent

### Day 1 - Create Env

1. Deployed a clean Online Boutique: an application we did not write, to test that the agent works on any application.
2. Audited what is already broken in the upstream version (replicas, probes, PDBs, Redis). Without this step the agent would find real weaknesses we did not know about and be penalized for them as false positives.
3. Ran `dependency-check.sh`, which scales each service down in turn and checks what the user sees. This showed which failures the site survives and which take it down.
4. Investigated the `000` results and found a slow failure: when a dependency disappears, the frontend blocks for about 20 seconds instead of failing fast. This only showed up through experiment.
5. Hardened 4 services to 2 replicas, so the planted weaknesses are subtle and not hidden behind a single replica.
6. Planted 4 weaknesses with Kustomize patches, and verified W1 with a real node drain.
7. Recorded all of it in one file: `ground_truth.yaml`. This file will help us to check the Agent preformence in the CI pipline, evrey cahnge that will be made to the AGENT will run on the butiqe app and the result will be tested aginst the finding in the `ground_truth.yaml`