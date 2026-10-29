# simplicio-videos

> מנוע וידאו דטרמיניסטי המונע על ידי סוכנים: חוזה YAML נכנס, קובץ MP4 יוצא, ומסביב ערכת כלים לאודיו, וידאו, קול, החלפת דמויות, תכנון פרסומים ברשתות חברתיות, רישוי נכסים וחיפוש ברשת.

[אנגלית וכל השפות: README הקנוני](../README.md) · [פורטוגזית](../README.pt-BR.md)

## מה הוא עושה

- **מחוזה ל-MP4:** בודק חוזה YAML, מייצר קריינות, מרנדר באופן דטרמיניסטי עם HyperFrames ומיקס של -14 LUFS, וכותב קובץ manifest. אף מודל שפה (LLM) לא פועל במסלול הרינדור.
- **קול:** ספקים `file`, `local` (Kokoro-82M), `gemini`, `voxcpm`, `openvoice` ו-`voicestudio` (אפליקציה מקומית). `elevenlabs` ו-`xai` הם stubs בלבד, ללא מימוש.
- **אודיו ווידאו (`media`):** בדיקת קובץ (probe), חילוץ אודיו, גליונות פריימים, כתוביות, מסכות תיבה, דיבוב והורדת סרטון ציבורי אחד עם רשומת מקור (provenance).
- **חיתוכים אנכיים (`shorts`):** קטעים בפורמט 9:16 מתוך סרטון ארוך, מדורגים לפי כללים קבועים מתוך תמלול מילה-מילה.
- **עריכת EDL (`edit`):** הסוכן כותב את ה-EDL, ועוזרי video-use (גרסה מוצמדת) מפעילים את ffmpeg.
- **תבניות וקטלוגים:** 14 תבניות לפי מגזר (8 מוכנות לרינדור), 55 פריטים בקטלוג התנועה, 50 פורמטים לפרסומות ו-50 זוויות.
- **החלפת דמויות ומשימות (`swap`, `jobs`):** החלפה בתשלום דרך שישה מתאמים, עם הערכת עלות ותקרה בדולרים (US$), ומופעלת רק מהטרמינל; משימות רקע ל-swap ולקול מקומי.
- **מסלולי הפקה חיצוניים:** Hypit, OpenMontage, OpenCut, Toonflow ו-MoneyPrinterTurbo, כל אחד מוצמד ומופעל כתוכנית נפרדת, ולעולם לא מיובא.
- **תכנון פרסום (`social`):** בודק סרטון מול המגבלות של כל רשת וכותב תוכנית. **לעולם לא מפרסם.**
- **ספרייה מורשית (`openverse`):** חיפוש, הורדה בטוחה, בדיקה לכל בקשה, וייצוא עם קרדיטים.
- **חיפוש ברשת (`busca`):** שאילתות וקריאת דפים דרך TinyFish, עם מקור ותאריך לכל תוצאה ותקרה יומית לקריאות.
- **מסלול UGC:** קובצי פרומפטים לדמויות סינתטיות וצינור ידני, מחוץ לרינדור.
- **שילוב עם סוכנים:** שרת MCP עם 19 כלי `video.*`, שישה skills, ו-`install` להתקנה ב-11 מארחי סוכנים.
- **תפעול:** סטטוס, כלים מוצמדים, אבחון, סביבת עבודה, עדכונים וכניסה משותפת ל-Simplicio.

## התחלה מהירה

```bash
gh repo clone simpletibr/simplicio-videos && cd simplicio-videos
pip install -e .                      # `simplicio-video` command (Python >= 3.10); rendering needs Node >= 22 and ffmpeg
simplicio-video setup                 # first run
simplicio-video install               # copy the skills into your agent host (project; --global for the home folder)
simplicio-video doctor                # check what is missing

cd clients/<cliente>/<campanha>       # a client project with a contract.yaml
simplicio-video validate contract.yaml
simplicio-video voice contract.yaml   # narration; local draft voice or --provider file|gemini|voxcpm|openvoice|voicestudio
simplicio-video render contract.yaml  # out/<cliente>-<campanha>.mp4 + render.manifest.json
```

## מגבלות

- **כיסוי MCP:** `media`, `shorts`, `tools`, `status`, `doctor` ו-`install` זמינים כרגע רק דרך CLI.
- **מתאמי החלפה לא מאומתים:** `fal`, `wavespeed`, `kie` ו-`alibaba` נכתבו לפי תיעוד ציבורי ולא נבדקו מול ה-APIs החיים.
- **אין פרסום:** המנוע לעולם אינו מפרסם או מעלה תוכן לרשת חברתית.
- **פלטפורמות:** החבילה מסווגת ל-Linux; macOS ו-Windows לא אומתו על מחשבים אמיתיים.

הסיכום הזה קצר יותר מ-[README הקנוני](../README.md) ועשוי להיות פחות מעודכן ממנו.
