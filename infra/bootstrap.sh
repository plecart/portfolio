#!/usr/bin/env bash
# Amorçage d'un VPS neuf (cadrage §6.7 point 1, ADR 0002, brief de #16 décision 7) : Docker,
# utilisateur de déploiement, pare-feu SSH seul, `fail2ban`, mises à jour automatiques, SSH par
# clés, connexion à GHCR, `.env` écrit depuis les secrets, puis la pile démarrée, avec le rôle
# Postgres de la sauvegarde. La procédure qui l'entoure — copier les fichiers, créer les secrets —
# est dans `infra/RUNBOOK.md`.
#
# En root sur le VPS, à côté de `compose.yml` et de `prod.env.example` copiés du même commit :
#   sudo bash bootstrap.sh         amorce le VPS ; relancé, il ne change rien
#   sudo bash bootstrap.sh NOM…    renouvelle ces valeurs : une variable de `prod.env.example`,
#                                  `GHCR_TOKEN` (jeton du registre) ou `DEPLOY_KEY` (clé de la CI)
#
# Les secrets se saisissent au clavier, sans écho — jamais en argument, que l'historique du shell
# et la liste des processus garderaient. Une valeur déjà écrite est gardée : le mot de passe
# Postgres, en particulier, est celui que la base a reçu à sa création.
#
# Non testé automatiquement (PRD « Décisions de test, Socle ») : vérifié à la main par #25 — sauf la
# SQL du rôle de la sauvegarde, que `infra/tests/test_backup_image.py` joue sur l'image Postgres.

set -euo pipefail

# L'utilisateur qui déploie : membre du groupe `docker`, donc l'équivalent de `root` (doc Docker
# « Docker Engine security ») — sans `sudo`, joint par la seule clé de la CI.
DEPLOY_USER=deploy
# Le dossier de la pile, où le job `deploy` de la CI dépose `compose.yml` et réécrit `IMAGE_TAG`.
STACK_DIR=/srv/portfolio
# Le propriétaire des paquets privés `ghcr.io/plecart/portfolio-*` (ADR 0014).
REGISTRY_USER=plecart

# Les secrets que le script engendre : 32 octets en hexadécimal, donc 64 caractères — au-delà des
# 50 que `Env` exige de `SECRET_KEY` —, sans `$` ni caractère réservé d'URL : le mot de passe
# Postgres entre tel quel dans `DATABASE_URL`.
GENERATED=(SECRET_KEY POSTGRES_PASSWORD BACKUP_POSTGRES_PASSWORD)
# Les valeurs que le modèle fixe lui-même, reprises telles quelles.
FROM_MODEL=(POSTGRES_USER POSTGRES_DB BACKUP_POSTGRES_USER)
# Les valeurs renouvelables qui ne vivent pas dans le `.env`.
OTHER_SECRETS=(GHCR_TOKEN DEPLOY_KEY)
# Les valeurs du `.env`, par nom, telles que `write_env` les a écrites — `start_stack` les lit :
# `main` appelle toujours `write_env` avant lui.
declare -A VALUES=()

export DEBIAN_FRONTEND=noninteractive

step() { printf '\n== %s\n' "$*"; }
die() {
	printf 'bootstrap.sh : %s\n' "$*" >&2
	exit 1
}
as_deploy() { sudo -u "$DEPLOY_USER" -H "$@"; }
stack() { (cd "$STACK_DIR" && as_deploy docker compose "$@"); }
contains() {
	local needle=$1
	shift
	[[ " $* " == *" $needle "* ]]
}

# 0. Les préalables : root, Ubuntu LTS (ADR 0002), les deux fichiers du dépôt à côté du script.
check_host() {
	[[ $(id -u) -eq 0 ]] || die "à lancer en root (sudo bash bootstrap.sh)"
	# shellcheck source=/dev/null
	. /etc/os-release
	[[ $ID == ubuntu && $VERSION == *LTS* ]] || die "Ubuntu LTS attendu, trouvé : $PRETTY_NAME"
	[[ -f compose.yml && -f prod.env.example ]] ||
		die "compose.yml et prod.env.example doivent être à côté du script"
}

# 1. Les paquets du système : pare-feu, `fail2ban` et son lecteur du journal de systemd, mises à
#    jour automatiques, et de quoi tirer la clé du dépôt de Docker. `--no-upgrade` ici et à
#    l'étape 2 : un paquet présent n'est pas mis à niveau — une relance, pour renouveler un secret,
#    ne redémarre pas Docker et la pile ; les mises à jour ont leur procédure (`infra/RUNBOOK.md`).
install_packages() {
	step "Paquets du système"
	apt-get update
	apt-get install -y --no-upgrade ca-certificates curl openssl ufw fail2ban python3-systemd \
		unattended-upgrades
}

# 2. Docker Engine et le greffon Compose, depuis le dépôt de Docker (doc Docker « Install Docker
#    Engine on Ubuntu ») : celui d'Ubuntu ne suit pas — les sondes de `compose.yml` demandent
#    Docker Engine 25 ou plus (`start_interval`).
install_docker() {
	step "Docker Engine"
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
	chmod a+r /etc/apt/keyrings/docker.asc
	cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
	apt-get update
	apt-get install -y --no-upgrade docker-ce docker-ce-cli containerd.io docker-compose-plugin
}

# 3. Les mises à jour de sécurité d'Ubuntu, chaque jour, sans intervention. Docker, venu d'un autre
#    dépôt, se met à jour à la main (`infra/RUNBOOK.md`).
enable_unattended_upgrades() {
	step "Mises à jour automatiques"
	cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
}

# 4. L'utilisateur de déploiement, et la clé publique de la CI comme seule clé autorisée.
create_deploy_user() {
	step "Utilisateur $DEPLOY_USER"
	id -u "$DEPLOY_USER" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$DEPLOY_USER"
	usermod -aG docker "$DEPLOY_USER"
	local ssh_dir="/home/$DEPLOY_USER/.ssh"
	install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$ssh_dir"
	if contains DEPLOY_KEY "${RENEW[@]}" || [[ ! -s $ssh_dir/authorized_keys ]]; then
		local key
		read -r -p "Clé publique de déploiement (ligne ssh-ed25519 …) : " key
		[[ $key == ssh-ed25519\ * ]] || die "une clé publique ssh-ed25519 est attendue"
		printf '%s\n' "$key" >"$ssh_dir/authorized_keys"
	fi
	chown "$DEPLOY_USER:$DEPLOY_USER" "$ssh_dir/authorized_keys"
	chmod 600 "$ssh_dir/authorized_keys"
}

# 5. OpenSSH par clés uniquement (ADR 0002). Le fichier est lu avant ceux d'un fournisseur (ordre
#    alphabétique de `sshd_config.d/`, première valeur retenue) ; `sshd -T` vérifie la valeur en
#    vigueur. Refus si l'administrateur n'a aucune clé : couper les mots de passe fermerait le VPS.
harden_ssh() {
	step "SSH par clés"
	local admin_home
	admin_home=$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)
	[[ -s $admin_home/.ssh/authorized_keys ]] ||
		die "aucune clé autorisée pour ${SUDO_USER:-root} : les mots de passe resteraient le seul accès"
	cat >/etc/ssh/sshd_config.d/00-portfolio.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
	sshd -t
	systemctl reload ssh
	# `grep` sans `-q` : il lit tout, `sshd` n'écrit jamais dans un tube fermé — sous `pipefail`,
	# le signal qu'il recevrait ferait échouer la vérification à tort.
	sshd -T | grep -x 'passwordauthentication no' >/dev/null ||
		die "un autre réglage rouvre les mots de passe"
}

# 6. Le pare-feu : tout entrant refusé, sauf SSH. Aucun port de la pile n'est publié
#    (`compose.yml`) — Docker contournerait `ufw` pour un port publié.
enable_firewall() {
	step "Pare-feu"
	ufw default deny incoming
	ufw default allow outgoing
	ufw allow OpenSSH
	ufw --force enable
}

# 7. `fail2ban` sur SSH, lu dans le journal de systemd — ce que le paquet d'Ubuntu 24.04 pose déjà,
#    épinglé ici contre un changement du paquet.
enable_fail2ban() {
	step "fail2ban"
	cat >/etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled = true
backend = systemd
EOF
	systemctl enable fail2ban
	systemctl restart fail2ban
}

# 8. La connexion de l'utilisateur de déploiement à GHCR, où les images sont privées : un jeton
#    *classic* de portée `read:packages` — le seul que GHCR accepte (doc GitHub « Working with the
#    Container registry ») —, conservé hors du serveur. Docker le garde dans la configuration de
#    l'utilisateur, jamais dans le `.env`.
login_registry() {
	step "Connexion à GHCR"
	if contains GHCR_TOKEN "${RENEW[@]}" ||
		! grep -qs '"ghcr.io"' "/home/$DEPLOY_USER/.docker/config.json"; then
		local token
		read -r -s -p "Jeton GitHub classic, portée read:packages (sans écho) : " token
		echo
		printf '%s' "$token" | as_deploy docker login ghcr.io -u "$REGISTRY_USER" --password-stdin
	fi
}

# Une nouvelle valeur pour une variable du modèle : engendrée, reprise du modèle, ou saisie — sans
# écho pour un secret, vérifiée pour l'étiquette des images. Un secret se reconnaît à son nom, ou
# se nomme ici quand son nom ne le dit pas : l'adresse de ping de `backup`, avec laquelle n'importe
# qui signale une sauvegarde réussie (brief de #23, décision 9).
new_value() {
	local name=$1 value
	if contains "$name" "${GENERATED[@]}"; then
		openssl rand -hex 32
		return
	fi
	if contains "$name" "${FROM_MODEL[@]}"; then
		sed -n "s/^$name=//p" prod.env.example
		return
	fi
	case $name in
	*TOKEN* | *SECRET* | *PASSWORD* | *KEY* | BACKUP_PING_URL)
		read -r -s -p "$name (sans écho) : " value
		echo >&2
		;;
	IMAGE_TAG) read -r -p "IMAGE_TAG — SHA complet d'un commit publié de main : " value ;;
	*) read -r -p "$name : " value ;;
	esac
	if [[ $name == IMAGE_TAG && ! $value =~ ^[0-9a-f]{40}$ ]]; then
		die "IMAGE_TAG doit être un SHA complet, jamais latest"
	fi
	printf '%s\n' "$value"
}

# 9. Le `.env` de la pile : les variables de `prod.env.example`, et elles seules, chacune entre
#    apostrophes — Compose prend alors la valeur telle quelle, sans interpoler un `$` (doc Docker
#    « .env file syntax »). Une valeur déjà écrite est gardée, sauf si elle est à renouveler ; un
#    mot de passe Postgres renouvelé change d'abord dans la base, qui garde le sien dans son volume.
write_env() {
	step "Fichier .env"
	install -d -m 750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$STACK_DIR"
	# Le Compose du premier démarrage ; ensuite, le job `deploy` dépose celui de chaque commit.
	[[ -f $STACK_DIR/compose.yml ]] ||
		install -m 640 -o "$DEPLOY_USER" -g "$DEPLOY_USER" compose.yml "$STACK_DIR/compose.yml"

	local env_file=$STACK_DIR/.env name value
	local -A current=()
	if [[ -f $env_file ]]; then
		while IFS='=' read -r name value; do
			value=${value#\'}
			current[$name]=${value%\'}
		done < <(grep -E '^[A-Z_][A-Z0-9_]*=' "$env_file")
	fi

	local lines=()
	for name in "${NAMES[@]}"; do
		if contains "$name" "${RENEW[@]}" || [[ -z ${current[$name]:-} ]]; then
			value=$(new_value "$name")
		else
			value=${current[$name]}
		fi
		[[ -n $value && $value != *\'* && $value != *$'\n'* ]] ||
			die "$name : valeur vide, ou portant une apostrophe ou un saut de ligne"
		if [[ $name == POSTGRES_PASSWORD && -n ${current[$name]:-} && $value != "${current[$name]}" ]]; then
			change_postgres_password "${current[POSTGRES_USER]}" "${current[POSTGRES_DB]}" "$value"
		fi
		VALUES[$name]=$value
		lines+=("$name='$value'")
	done

	local draft
	draft=$(mktemp "$STACK_DIR/.env.XXXXXX")
	printf '%s\n' "${lines[@]}" >"$draft"
	chown "$DEPLOY_USER:$DEPLOY_USER" "$draft"
	chmod 600 "$draft"
	mv "$draft" "$env_file"
}

# La SQL de l'entrée standard, jouée dans la base (2ᵉ argument) sous le rôle de l'application (1ᵉʳ),
# qui l'administre — jamais en argument, qu'un `ps` lirait.
run_sql() {
	stack exec -T postgres psql --quiet -v ON_ERROR_STOP=1 -U "$1" -d "$2"
}

# Le nouveau mot de passe (3ᵉ argument) du rôle (1ᵉʳ) dans la base (2ᵉ) qui tourne. Pile arrêtée :
# impossible, la base garderait l'ancien.
change_postgres_password() {
	[[ -n $(stack ps --status running --quiet postgres) ]] ||
		die "démarrer la pile avant de renouveler POSTGRES_PASSWORD (infra/RUNBOOK.md)"
	printf "ALTER ROLE \"%s\" PASSWORD '%s';\n" "$1" "$3" | run_sql "$1" "$2"
}

# La SQL du rôle de `backup` (brief de #23, décision 3), nommé par le 1ᵉʳ argument : connexion et
# lecture de toutes les données, rien d'autre. Rejouable : le rôle est créé s'il manque, et reçoit
# à chaque passage le mot de passe du 2ᵉ argument — c'est ainsi qu'on le renouvelle. Le nom vient du
# modèle versionné, le mot de passe est engendré en hexadécimal : ni l'un ni l'autre ne porte de
# guillemet ni d'apostrophe. `infra/tests/` la joue sur l'image Postgres de la pile.
backup_role_sql() {
	cat <<EOF
SELECT 'CREATE ROLE "$1" LOGIN IN ROLE pg_read_all_data'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$1')
\gexec
ALTER ROLE "$1" PASSWORD '$2';
EOF
}

# 10. La pile, aux images de `IMAGE_TAG`, attendue saine comme le fait le job `deploy` — la base
#     d'abord, puis le rôle de `backup`, dont la sonde ouvre une session, puis le reste. Sans
#     `pull` : `up` tire les images absentes (`pull_policy` par défaut, `missing`) et ne contacte
#     pas le registre pour une image présente — un renouvellement, qui a déjà changé le mot de
#     passe dans la base, recrée `api` et `worker` même si GHCR refuse le jeton.
start_stack() {
	step "Pile"
	local up=(up -d --wait --wait-timeout 300)
	stack "${up[@]}" postgres
	backup_role_sql "${VALUES[BACKUP_POSTGRES_USER]}" "${VALUES[BACKUP_POSTGRES_PASSWORD]}" |
		run_sql "${VALUES[POSTGRES_USER]}" "${VALUES[POSTGRES_DB]}"
	stack "${up[@]}"
	stack ps
}

main() {
	cd "$(dirname "$0")"
	check_host
	mapfile -t NAMES < <(grep -oE '^[A-Z_][A-Z0-9_]*' prod.env.example)
	RENEW=("$@")
	local name
	for name in "${RENEW[@]}"; do
		contains "$name" "${NAMES[@]}" "${OTHER_SECRETS[@]}" ||
			die "$name : ni variable de prod.env.example, ni ${OTHER_SECRETS[*]}"
	done

	install_packages
	install_docker
	enable_unattended_upgrades
	create_deploy_user
	harden_ssh
	enable_firewall
	enable_fail2ban
	login_registry
	write_env
	start_stack

	step "Fait"
	echo "Empreinte de l'hôte, pour le secret DEPLOY_KNOWN_HOSTS (infra/RUNBOOK.md) :"
	cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub
}

# Exécuté, il amorce ; chargé par `source`, il ne fait que définir ses fonctions.
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
	main "$@"
fi
