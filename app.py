import os
import re
import subprocess
from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from werkzeug.utils import secure_filename

# Impostiamo template_folder='.' per cercare i file HTML nella cartella corrente (insieme ad app.py)
app = Flask(__name__, template_folder='.')
app.secret_key = "supersegreto"  # Necessario per i messaggi flash (errori/info)

# Configuriamo le cartelle
UPLOAD_FOLDER = 'uploads'
DOWNLOAD_FOLDER = 'downloads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # 1. Controlla se c'è il file
        if 'file' not in request.files:
            flash('Nessun file selezionato')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('Nessun file selezionato')
            return redirect(request.url)

        if file and file.filename.endswith('.tex'):
            # Sanitizziamo il nome del file per sicurezza
            original_filename = file.filename
            filename = secure_filename(original_filename)
            
            # Leggiamo il contenuto per rimuovere i disegni (TikZ) che causano errori
            # errors='replace' evita crash se il file ha caratteri strani non UTF-8
            content = file.read().decode('utf-8', errors='replace')
            
            # Rimuoviamo i blocchi \begin{tikzpicture}...\end{tikzpicture}
            # \s* gestisce eventuali spazi extra (es. \begin {tikzpicture})
            # Questo assicura che Pandoc si concentri solo su testo e formule
            content = re.sub(r'\\begin\s*\{tikzpicture\}.*?\\end\s*\{tikzpicture\}', '', content, flags=re.DOTALL)

            # Rimuoviamo anche le figure e includegraphics per evitare errori di file mancanti (immagini non caricate)
            content = re.sub(r'\\begin\s*\{figure\}.*?\\end\s*\{figure\}', '', content, flags=re.DOTALL)
            content = re.sub(r'\\includegraphics(\[.*?\])?\{.*?\}', '', content)

            # Correzione Extra: Rimuove i doppi dollari $$ attorno alle equation (errore comune che blocca Pandoc)
            content = re.sub(r'\$\$\s*(\\begin\{equation\}.*?\\end\{equation\})\s*\$\$', r'\1', content, flags=re.DOTALL)

            # Estrazione Metadati (Titolo, Autore, Data) dal contenuto LaTeX
            # Usiamo una regex che supporta un livello di annidamento di graffe (es. \textbf{...})
            # Questo ci permette di leggere \title{Il mio titolo} anche se è su più righe
            title_match = re.search(r'\\title\{((?:[^{}]|\{[^{}]*\})*)\}', content, re.DOTALL)
            author_match = re.search(r'\\author\{((?:[^{}]|\{[^{}]*\})*)\}', content, re.DOTALL)
            date_match = re.search(r'\\date\{((?:[^{}]|\{[^{}]*\})*)\}', content, re.DOTALL)

            # 2. Salva il file .tex pulito
            input_path = os.path.join(UPLOAD_FOLDER, filename)
            with open(input_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Nome del file di output
            output_filename = filename.replace('.tex', '.epub')
            output_path = os.path.join(DOWNLOAD_FOLDER, output_filename)

            # Determinazione del Titolo
            epub_title = None
            if title_match:
                # Puliamo il titolo da comandi LaTeX (es. \Huge) per evitare titoli vuoti o "sporchi"
                raw_title = title_match.group(1)
                clean_title = re.sub(r'\\[a-zA-Z]+', '', raw_title) # Rimuove \Huge, \bfseries ecc.
                clean_title = re.sub(r'[{}]', '', clean_title).strip()
                if clean_title:
                    epub_title = clean_title

            if not epub_title:
                # Fallback: nome del file pulito se manca \title o se il contenuto era solo formattazione
                epub_title = original_filename.replace('.tex', '').replace('_', ' ')

            # 3. Esegui Pandoc
            # -t epub3: specifica la versione 3 (più compatibile)
            cmd = [
                'pandoc', input_path, 
                '-f', 'latex', 
                '-t', 'epub3', 
                '--mathml', 
                '--metadata', f'title={epub_title}',
                '-o', output_path
            ]

            # Aggiungiamo Autore e Data se presenti nel file
            if author_match:
                cmd.extend(['--metadata', f'author={author_match.group(1).strip()}'])
            if date_match:
                cmd.extend(['--metadata', f'date={date_match.group(1).strip()}'])

            try:
                # Eseguiamo il comando
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                
                # Se ha successo, invia il file all'utente
                return send_file(output_path, as_attachment=True)

            except subprocess.CalledProcessError as e:
                # 4. Gestione Errori: Mostra l'errore (spesso make4ht scrive in stdout)
                error_message = f"Errore durante la conversione:\n{e.stdout}\n{e.stderr}"
                flash(error_message)
                return redirect(url_for('index'))
        else:
            flash('Per favore carica un file .tex valido.')
            return redirect(request.url)

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5001)
