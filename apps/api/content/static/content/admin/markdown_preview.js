/*
 * Aperçu Markdown de l'admin (brief de #8, décisions 1 et 2) : sous chaque champ Markdown, le rendu
 * du texte se rafraîchit une courte pause après la dernière frappe, sans enregistrer.
 *
 * Le serveur rend l'aperçu de la valeur avec la page (`MarkdownTextarea`, `content/preview.py`) :
 * rien à demander au chargement, ni sur un écran revenu en erreur. Le script ne rafraîchit qu'à la
 * saisie, par un seul écouteur sur le document : une ligne ajoutée après le chargement par le
 * bouton de Django — copie de la ligne modèle, bloc d'aperçu compris — est couverte sans rien
 * brancher.
 *
 * Chaque bloc `.markdown-field` réunit une zone de texte et son aperçu (`.markdown-preview`), et
 * porte l'adresse de la vue (`data-preview-url`) et le message d'échec (`data-preview-failed`). Le
 * texte part en POST, avec le jeton CSRF du formulaire en en-tête ; la vue renvoie le fragment
 * HTML assaini par `nh3`, inséré tel quel.
 *
 * Hors du chemin nominal : une requête en cours est annulée par la suivante — une réponse tardive
 * n'écrase jamais l'aperçu d'un texte plus récent ; une redirection — session expirée, renvoyée
 * vers la connexion — compte comme un échec, jamais comme un aperçu ; un échec montre le message,
 * que le rafraîchissement suivant remplace.
 */
"use strict";
{
    // La pause après la dernière frappe, en millisecondes (brief de #8, décision 2).
    const PREVIEW_DELAY_MS = 300;

    // Par bloc : le minuteur de la pause en cours, et la requête en cours.
    const timers = new WeakMap();
    const requests = new WeakMap();

    // Demande l'aperçu du texte du bloc et l'affiche, ou le message d'échec.
    const refresh = async (field) => {
        requests.get(field)?.abort();
        const request = new AbortController();
        requests.set(field, request);
        const preview = field.querySelector(".markdown-preview");
        try {
            const response = await fetch(field.dataset.previewUrl, {
                method: "POST",
                body: new URLSearchParams({ text: field.querySelector("textarea").value }),
                headers: {
                    "X-CSRFToken": field.closest("form").querySelector("[name=csrfmiddlewaretoken]")
                        .value,
                },
                redirect: "error",
                signal: request.signal,
            });
            if (!response.ok) {
                throw new Error(`aperçu refusé : ${response.status}`);
            }
            preview.innerHTML = await response.text();
        } catch (error) {
            if (error.name !== "AbortError") {
                preview.textContent = field.dataset.previewFailed;
            }
        }
    };

    document.addEventListener("input", (event) => {
        const field = event.target.closest && event.target.closest(".markdown-field");
        if (!field) {
            return;
        }
        clearTimeout(timers.get(field));
        timers.set(field, setTimeout(() => refresh(field), PREVIEW_DELAY_MS));
    });
}
