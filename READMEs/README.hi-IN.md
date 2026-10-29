# simplicio-videos

> एजेंट-संचालित एक नियतात्मक (deterministic) वीडियो इंजन: इनपुट में YAML अनुबंध, आउटपुट में MP4, और उसके चारों ओर ऑडियो, वीडियो, वॉइस, कैरेक्टर स्वैप, सोशल प्लानिंग, एसेट लाइसेंसिंग और वेब रिसर्च के टूल।

[अंग्रेज़ी और सभी भाषाएँ: मूल README](../README.md) · [पुर्तगाली](../README.pt-BR.md)

## यह क्या करता है

- **कॉन्ट्रैक्ट से MP4:** YAML कॉन्ट्रैक्ट को सत्यापित करता है, नैरेशन बनाता है, HyperFrames से नियतात्मक तरीके से रेंडर करता है (मिक्स -14 LUFS पर) और एक मेनिफेस्ट लिखता है। रेंडर पथ में कोई LLM नहीं चलता।
- **वॉइस:** प्रदाता `file`, `local` (Kokoro-82M), `gemini`, `voxcpm`, `openvoice` और `voicestudio` (स्थानीय ऐप)। `elevenlabs` और `xai` स्टब (stub) हैं, यानी अभी लागू नहीं।
- **ऑडियो और वीडियो (`media`):** प्रोब, ऑडियो निकालना, फ़्रेम शीट, सबटाइटल, बॉक्स मास्क, डबिंग, और एक सार्वजनिक वीडियो को उसके प्रोवेनेंस रिकॉर्ड के साथ डाउनलोड करना।
- **वर्टिकल कट (`shorts`):** शब्द-स्तरीय ट्रांसक्रिप्ट पर तय नियमों से स्कोर करके, लंबे वीडियो से 9:16 क्लिप।
- **EDL संपादन (`edit`):** एजेंट EDL लिखता है; पिन किए गए video-use के सहायक ffmpeg चलाते हैं।
- **टेम्पलेट और कैटलॉग:** 14 सेक्टर टेम्पलेट (8 रेंडर के लिए तैयार), 55 मोशन कैटलॉग प्रविष्टियाँ, 50 विज्ञापन प्रारूप और 50 एंगल।
- **कैरेक्टर स्वैप और जॉब्स (`swap`, `jobs`):** छह एडैप्टर के जरिए भुगतान-आधारित स्वैप, लागत अनुमान और US$ सीमा के साथ, केवल टर्मिनल से; swap और लोकल वॉइस के लिए बैकग्राउंड जॉब्स।
- **बाहरी प्रोडक्शन ट्रैक:** Hypit, OpenMontage, OpenCut, Toonflow और MoneyPrinterTurbo। हर एक पिन किया गया है और अलग प्रोग्राम के रूप में चलता है, कभी इम्पोर्ट नहीं होता।
- **सोशल प्लानिंग (`social`):** वीडियो को हर नेटवर्क की सीमाओं से जाँचता है और एक प्लान लिखता है। **यह कभी पोस्ट नहीं करता।**
- **लाइसेंस्ड लाइब्रेरी (`openverse`):** खोज, सुरक्षित डाउनलोड, हर अनुरोध के लिए समीक्षा, और क्रेडिट के साथ एक्सपोर्ट।
- **वेब रिसर्च (`busca`):** TinyFish के जरिए क्वेरी और पेज पढ़ना, हर परिणाम के साथ स्रोत और तारीख, और रोज़ की कॉल सीमा।
- **UGC ट्रैक:** सिंथेटिक किरदारों की प्रॉम्प्ट फ़ाइलें और मैनुअल पाइपलाइन; रेंडर से बाहर।
- **एजेंट इंटीग्रेशन:** 19 `video.*` टूल वाला MCP सर्वर, 6 skills, और 11 एजेंट होस्ट में इंस्टॉल करने के लिए `install`।
- **ऑपरेशन:** स्टेटस, पिन किए गए टूल, डायग्नोस्टिक्स, वर्कस्पेस, अपडेट और साझा Simplicio लॉगिन।

## क्विक स्टार्ट

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

## सीमाएँ

- **MCP कवरेज:** `media`, `shorts`, `tools`, `status`, `doctor` और `install` अभी केवल CLI में उपलब्ध हैं।
- **असत्यापित स्वैप एडैप्टर:** `fal`, `wavespeed`, `kie` और `alibaba` सार्वजनिक दस्तावेज़ों से लिखे गए हैं और लाइव APIs पर जाँचे नहीं गए हैं।
- **कोई पब्लिशिंग नहीं:** इंजन कभी किसी सोशल नेटवर्क पर पोस्ट या अपलोड नहीं करता।
- **प्लेटफ़ॉर्म:** पैकेज Linux के लिए वर्गीकृत है; macOS और Windows वास्तविक मशीनों पर पुष्ट नहीं हैं।

यह सारांश [मूल README](../README.md) से छोटा है और उससे पीछे हो सकता है।
