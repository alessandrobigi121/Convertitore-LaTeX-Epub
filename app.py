import os
import re
import subprocess
import zipfile
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

        if file and (file.filename.endswith('.tex') or file.filename.endswith('.zip')):
            # Sanitizziamo il nome del file per sicurezza
            original_filename = file.filename
            filename = secure_filename(original_filename)
            
            # Percorsi assoluti per gestire correttamente la working directory di Pandoc
            base_dir = os.path.abspath(os.path.dirname(__file__))
            abs_upload_folder = os.path.join(base_dir, UPLOAD_FOLDER)
            abs_download_folder = os.path.join(base_dir, DOWNLOAD_FOLDER)
            
            input_path = os.path.join(abs_upload_folder, filename)
            file.save(input_path)

            # Variabili per gestire ZIP vs TEX singolo
            tex_file_path = input_path
            work_dir = abs_upload_folder
            keep_images = False

            # Gestione ZIP (Estrazione)
            if filename.endswith('.zip'):
                extract_folder = os.path.join(abs_upload_folder, os.path.splitext(filename)[0])
                os.makedirs(extract_folder, exist_ok=True)
                with zipfile.ZipFile(input_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_folder)
                
                # Cerchiamo il file .tex principale nello zip
                found_tex = False
                for root, dirs, files in os.walk(extract_folder):
                    # Ignoriamo la cartella di sistema __MACOSX creata dai Mac
                    if '__MACOSX' in root:
                        continue

                    for f in files:
                        # Ignoriamo i file fantasma che iniziano con ._ (metadati Mac)
                        if f.endswith('.tex') and not f.startswith('._'):
                            tex_file_path = os.path.join(root, f)
                            work_dir = root # Pandoc deve girare qui per trovare le immagini
                            found_tex = True
                            break
                    if found_tex: break
                
                if not found_tex:
                    flash('Nessun file .tex trovato nello ZIP.')
                    return redirect(request.url)
                
                keep_images = True # Se è uno zip, presumiamo ci siano le immagini

            # Leggiamo il contenuto del file .tex identificato
            with open(tex_file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            # FIX: Rimuoviamo caratteri di controllo non validi per XML (0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F)
            # Questo risolve errori come "PCDATA invalid Char value 5" e "Char 0x0 out of allowed range"
            content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', content)
            
            # Rimuoviamo i blocchi \begin{tikzpicture}...\end{tikzpicture}
            # \s* gestisce eventuali spazi extra (es. \begin {tikzpicture})
            # Questo assicura che Pandoc si concentri solo su testo e formule
            content = re.sub(r'\\begin\s*\{tikzpicture\}.*?\\end\s*\{tikzpicture\}', '', content, flags=re.DOTALL)

            # Rimuoviamo le immagini SOLO se non siamo in modalità ZIP (quindi mancano i file sorgente)
            if not keep_images:
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

            # Salva il file .tex pulito (sovrascrivendo quello estratto o caricato)
            with open(tex_file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Recuperiamo il formato desiderato dal form (default: epub)
            # Nota: Assicurati di avere <select name="output_format"> nel tuo HTML
            target_format = request.form.get('output_format', 'epub')
            
            # Nome base per l'output (dal nome del file originale, senza estensione)
            output_base_name = os.path.splitext(original_filename)[0]
            
            # Configuriamo estensione e argomenti in base al formato
            if target_format == 'docx':
                output_filename = output_base_name + '.docx'
                # Per Word non usiamo --mathml ma lasciamo la gestione standard
                pandoc_output_args = ['-t', 'docx']
            else:
                # Default: EPUB
                output_filename = output_base_name + '.epub'
                pandoc_output_args = ['-t', 'epub3', '--mathml']
                # Aggiungiamo CSS personalizzato se esiste
                css_path = os.path.join(base_dir, 'epub.css')
                if os.path.exists(css_path):
                    pandoc_output_args.extend(['--css', css_path])

            output_path = os.path.join(abs_download_folder, output_filename)

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
                epub_title = output_base_name.replace('_', ' ')

            # 3. Esegui Pandoc
            # -t epub3: specifica la versione 3 (più compatibile)
            cmd = [
                'pandoc', tex_file_path, 
                '-f', 'latex', 
            ] + pandoc_output_args + [
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
                # cwd=work_dir è fondamentale per far trovare le immagini relative (es. img/foto.jpg) a Pandoc
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=work_dir)
                
                # Se ha successo, invia il file all'utente
                response = send_file(output_path, as_attachment=True)

                # Impostiamo un cookie per segnalare al browser che il download è iniziato
                token = request.form.get('download_token')
                if token:
                    response.set_cookie('download_token', token, max_age=60)
                
                return response

            except subprocess.CalledProcessError as e:
                # 4. Gestione Errori: Mostra l'errore (spesso make4ht scrive in stdout)
                error_message = f"Errore durante la conversione:\n{e.stdout}\n{e.stderr}"
                flash(error_message)
                return redirect(url_for('index'))
        else:
            flash('Per favore carica un file .tex o .zip valido.')
            return redirect(request.url)

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5001)
