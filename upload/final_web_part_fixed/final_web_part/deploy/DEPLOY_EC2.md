# Deploiement EC2 — ALife Neuroevolution Simulation

## Architecture

```
Machine locale                    EC2 (Ubuntu)
┌──────────────┐     SSH/SCP     ┌─────────────────────┐
│  alife-sim/  │ ──────────────► │  /var/www/alife-sim │
│  (code + venv)│                 │  ├── index.html     │
│              │  deploy_ec2.sh  │  ├── alife-sim.apk  │
│  pygbag .    │ ──────────────► │  ├── alife-sim.tar.gz│
│  build/web/  │                 │  └── favicon.png    │
└──────────────┘                 │                     │
                                 │  nginx :80 ────────┼──► Client navigateur
                                 └─────────────────────┘
```

Le build pygbag genere des fichiers **100% statiques** (HTML + JS + WASM + APK archive).
Aucun serveur Python n'est necessaire sur l'EC2 — **nginx sert uniquement les fichiers statiques**.
La simulation tourne entierement dans le navigateur du client via Pyodide (Python/WASM).

---

## Methode 1 — Deploiement en une commande (depuis votre machine)

```bash
# Build + transfert + installation nginx en une seule commande
./deploy/deploy_from_local.sh ubuntu@<IP_DE_VOTRE_EC2>
```

Ce script fait tout :
1. Lance `pygbag .` pour regenerer le build
2. Copie les fichiers sur l'EC2 via SCP
3. Execute le script d'installation nginx a distance

---

## Methode 2 — Deploiement manuel etape par etape

### 1. Build en local

```bash
cd alife-sim
source venv/bin/activate
pygbag .
# Fichiers generes dans build/web/
```

### 2. Lancer une instance EC2

- **AMI** : Ubuntu 22.04 LTS ou 24.04 LTS
- **Type** : t2.micro (gratuit tier) ou t3.small
- **Security Group** : ouvrir le port 80 (HTTP) en inbound
- **Storage** : 8 Go (default) suffit largement

### 3. Transférer les fichiers

```bash
scp -r build/web/* ubuntu@<IP>:/tmp/alife-deploy/
```

### 4. Installer sur l'EC2

```bash
ssh ubuntu@<IP>
sudo mkdir -p /var/www/alife-sim
sudo cp -r /tmp/alife-deploy/* /var/www/alife-sim/
sudo chown -R www-data:www-data /var/www/alife-sim
```

### 5. Configurer nginx

```bash
sudo apt update && sudo apt install -y nginx

sudo tee /etc/nginx/sites-available/alife-sim << 'EOF'
server {
    listen 80;
    server_name _;

    root /var/www/alife-sim;
    index index.html;

    # Cache pour les assets statiques
    location ~* \.(apk|wasm|js|css|png|jpg|ico|svg|woff2?)$ {
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # Pas de cache pour index.html
    location = /index.html {
        expires -1;
        add_header Cache-Control "no-store, no-cache, must-revalidate";
    }

    # Compression
    gzip on;
    gzip_types text/html text/css application/javascript application/wasm;
    gzip_min_length 256;

    # Headers COOP/COEP requis par Pyodide (SharedArrayBuffer)
    add_header Cross-Origin-Opener-Policy "same-origin" always;
    add_header Cross-Origin-Embedder-Policy "require-corp" always;

    # Types MIME
    types {
        application/wasm wasm;
        application/javascript mjs;
    }

    client_max_body_size 10M;
}
EOF

sudo ln -sf /etc/nginx/sites-available/alife-sim /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl reload nginx
```

### 6. Ouvrir le port dans le security group AWS

- Aller sur AWS Console → EC2 → Security Groups
- Selectionner le groupe de l'instance
- Inbound Rules → Add Rule :
  - Type : HTTP
  - Port : 80
  - Source : 0.0.0.0/0 (ou votre IP pour plus de securite)

### 7. Acceder a la simulation

Ouvrir dans un navigateur :
```
http://<IP_DE_VOTRE_EC2>
```

> **Important** : Au premier chargement, Pyodide telecharge le runtime Python/WASM
> (~10-15 Mo). Le chargement peut prendre 5-10 secondes. Cliquez sur la page pour
> demarrer la simulation (geste utilisateur requis par le navigateur).

---

## Mise a jour

Pour mettre a jour la simulation apres une modification du code :

```bash
# En local
cd alife-sim
source venv/bin/activate
pygbag .
scp -r build/web/* ubuntu@<IP>:/var/www/alife-sim/
```

Les clients n'auront qu'a rafraichir leur page (Ctrl+F5) pour voir la nouvelle version.

---

## Optionnel — HTTPS avec Let's Encrypt

```bash
# Sur l'EC2
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d votre-domaine.com
```

---

## Troubleshooting

| Symptome | Cause probable | Solution |
|----------|---------------|----------|
| Page blanche | CORS/COEP manquants | Verifier les headers `Cross-Origin-Opener-Policy` et `Cross-Origin-Embedder-Policy` dans la config nginx |
| "Downloading..." infini | Fichiers manquants | Verifier que `alife-sim.tar.gz` et `index.html` sont dans `/var/www/alife-sim/` |
| Erreur wasm | MIME type incorrect | Verifier `types { application/wasm wasm; }` dans nginx |
| 403 Forbidden | Permissions | `sudo chown -R www-data:www-data /var/www/alife-sim` |
| Lent au chargement | Pas de gzip | Verifier que `gzip on;` est dans la config nginx |
| Security group | Port 80 bloque | Ouvrir le port 80 dans AWS Console |

---

## Cout estime (AWS Free Tier)

- **Instance t2.micro** : 750h/mois gratuit (1 an)
- **Stockage 8 Go EBS** : Inclus dans le free tier
- **Bande passante** : 100 Go/mois sortant gratuit (puis $0.09/Go)
- Un utilisateur qui charge la simulation consomme ~5-15 Mo au premier chargement
- Donc ~6600-20000 chargements/mois avant de sortir du free tier