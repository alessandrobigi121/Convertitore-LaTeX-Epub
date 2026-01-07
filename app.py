import os
import re
import subprocess
from flask import Flask, render_template, request, send_file, flash, redirect, url_for

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
            # Leggiamo il contenuto per rimuovere i disegni (TikZ) che causano errori
            # errors='replace' evita crash se il file ha caratteri strani non UTF-8
            content = file.read().decode('utf-8', errors='replace')
            
            # Rimuoviamo i blocchi \begin{tikzpicture}...\end{tikzpicture}
            # \s* gestisce eventuali spazi extra (es. \begin {tikzpicture})
            # Questo assicura che Pandoc si concentri solo su testo e formule
            content = re.sub(r'\\begin\s*\{tikzpicture\}.*?\\end\s*\{tikzpicture\}', '', content, flags=re.DOTALL)

            # Correzione Extra: Rimuove i doppi dollari $$ attorno alle equation (errore comune che blocca Pandoc)
            content = re.sub(r'\$\$\s*(\\begin\{equation\}.*?\\end\{equation\})\s*\$\$', r'\1', content, flags=re.DOTALL)

            # 2. Salva il file .tex pulito
            input_path = os.path.join(UPLOAD_FOLDER, file.filename)
            with open(input_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Nome del file di output
            output_filename = file.filename.replace('.tex', '.epub')
            output_path = os.path.join(DOWNLOAD_FOLDER, output_filename)

            # 3. Esegui Pandoc
            # Usiamo --mathml che è lo standard W3C per le formule negli EPUB
            cmd = ['pandoc', input_path, '-f', 'latex', '-t', 'epub', '--mathml', '--standalone', '-o', output_path]

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
