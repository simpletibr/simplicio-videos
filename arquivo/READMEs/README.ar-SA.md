# simplicio-videos

> محرك فيديو حتمي يقوده وكلاء: يدخل عقد YAML ويخرج ملف MP4، ومن حوله أدوات للصوت والفيديو والتعليق الصوتي (voice) واستبدال الشخصيات وتخطيط النشر الاجتماعي وترخيص الأصول والبحث على الويب.

[الإنجليزية وجميع اللغات: README المرجعي](../README.md) · [البرتغالية](../README.pt-BR.md)

## ما الذي يفعله

- **من العقد إلى MP4:** يتحقق من عقد YAML، ويولّد السرد الصوتي، ويصيّر الفيديو بشكل حتمي مع المزج عند -14 LUFS، ويكتب ملف البيان (manifest). لا يعمل أي نموذج لغوي (LLM) في مسار التصيير.
- **التعليق الصوتي:** المزوّدون `file` و`local` (Kokoro-82M) و`gemini` و`voxcpm` و`openvoice` و`voicestudio` (تطبيق محلي). `elevenlabs` و`xai` مجرد stubs (لم تُنفَّذ بعد).
- **الصوت والفيديو (`media`):** فحص الملف، واستخراج المسار الصوتي، وألواح الإطارات، والترجمات، وأقنعة المستطيلات، والدبلجة، وتنزيل فيديو عام واحد مع سجل المصدر (provenance).
- **القص العمودي (`shorts`):** مقاطع بنسبة 9:16 من فيديو طويل، تُقيَّم بقواعد ثابتة اعتمادًا على نص مكتوب كلمةً بكلمة.
- **المونتاج بقائمة EDL (`edit`):** يكتب الوكيل قائمة EDL، ويشغّل مساعدو video-use (إصدار مثبَّت) برنامج ffmpeg.
- **القوالب والكتالوجات:** 14 قالبًا قطاعيًا (8 منها جاهزة للتصيير)، و55 عنصرًا في كتالوج الحركة، و50 تنسيق إعلان، و50 زاوية.
- **استبدال الشخصيات والمهام (`swap`، `jobs`):** استبدال مدفوع عبر ستة محوّلات، مع تقدير للتكلفة وحد أقصى بالدولار الأمريكي (US$)، ويُشغَّل من الطرفية فقط؛ ومهام خلفية لـ swap والتعليق الصوتي المحلي.
- **المسارات الإنتاجية الخارجية:** Hypit وOpenMontage وOpenCut وToonflow وMoneyPrinterTurbo، كلٌّ منها مثبَّت ويعمل كبرنامج منفصل، ولا يُستورد أبدًا.
- **تخطيط النشر (`social`):** يتحقق من الفيديو وفق حدود كل شبكة ويكتب خطة. **لا ينشر أبدًا.**
- **المكتبة المرخّصة (`openverse`):** بحث، وتنزيل آمن، ومراجعة لكل طلب، وتصدير مع الإشارة إلى المؤلفين.
- **البحث على الويب (`busca`):** استعلامات وقراءة صفحات عبر TinyFish، مع المصدر والتاريخ لكل نتيجة، وحد يومي للاستدعاءات.
- **مسار UGC:** ملفات مطالبات (prompts) لشخصيات اصطناعية وخط إنتاج يدوي، خارج التصيير.
- **التكامل مع الوكلاء:** خادم MCP فيه 28 أداة من نوع `video.*`، و6 skills، و`install` للتثبيت في 11 مضيفًا للوكلاء.
- **العمليات:** الحالة، والأدوات المثبَّتة، والتشخيص، ومساحة العمل، والتحديثات، وتسجيل الدخول المشترك إلى Simplicio.

## البدء السريع

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

## الحدود

- **محوّلات استبدال غير مُتحقَّق منها:** `fal` و`wavespeed` و`kie` و`alibaba` كُتبت استنادًا إلى الوثائق العامة، ولم يُتحقَّق منها على واجهات برمجة التطبيقات الفعلية.
- **لا نشر:** لا ينشر المحرك شيئًا على الشبكات الاجتماعية ولا يرفعه إليها أبدًا.
- **المنصات:** صُنّفت الحزمة لنظام Linux، ولم يُؤكَّد عمل macOS وWindows على أجهزة حقيقية.

هذا الملخص أقصر من [README المرجعي](../README.md) وقد يتأخر عنه في التحديث.
