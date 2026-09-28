## 🧪 Test con un annuncio reale  
1. Prendi un annuncio che ti interessa (es. il "Sr Scientist, Lab Informatics" di Johnson & Johnson, o un annuncio su LinkedIn/Indeed).  
2. Copia il testo dell'annuncio (compresi requisiti e responsabilità) in un file jobs\nome_annuncio.txt.  
3. Sempre dal terminale in job-search-buddy, esegui:  
```bash
cd src
python analyze_job.py "..\jobs\nome_annuncio.txt"
```
Il report verrà salvato in outputs\ e stampato a schermo.  

## ⏱️ Cosa aspettarsi  
- Primo avvio: 1-3 minuti (il modello deve essere caricato in RAM).  
- Avvii successivi: più veloci, ma sempre nell'ordine di 30-90 secondi.  
- Output: un report Markdown strutturato con punteggio, match, gap e raccomandazione.  

## 💡 Trucchi  
- Se è troppo lento, aggiungi --extra-files solo quando serve (di default carica 3 file).  
- Se l'output è troppo generico, migliora i file del profilo: più numeri, più specificità, meno aggettivi.  
- Se il modello "inventa", aggiungi al system prompt: Never invent experiences not present in the profile. If unsure, say "not in profile". (puoi editare il file e riprovare).  