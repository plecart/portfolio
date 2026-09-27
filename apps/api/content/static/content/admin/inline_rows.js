/*
 * Lignes des tableaux en ligne de l'admin : les ordonner et les supprimer avant l'enregistrement
 * (ADR 0013). Générique : vaut pour tout tableau en ligne dont l'écran charge ce script, ce que fait
 * `SortableInline` (`content/inlines.py`).
 *
 * Tri. Chaque ligne, enregistrée ou neuve, porte une poignée (`.sortable-handle`). On fait glisser
 * la ligne par sa poignée — glisser-déposer natif du navigateur, sans bibliothèque —, ou on la
 * déplace par les flèches haut et bas quand la poignée a le focus. À l'envoi du formulaire, chaque
 * ligne gardée et remplie reçoit sa position dans l'ordre affiché, dans son champ caché
 * (`.sortable-position`) ; une ligne neuve restée vide garde sa position vide, et Django continue
 * de l'ignorer.
 *
 * Suppression. Django donne à une ligne neuve un bouton qui la retire de l'écran, et à une ligne
 * enregistrée une case « Supprimer ? » (`admin/edit_inline/tabular.html`, `admin/js/inlines.js`).
 * La case est cachée et remplacée par le bouton de Django, même classe et même libellé : un clic la
 * coche — elle reste la donnée envoyée — et retire la ligne de l'écran. La suppression en base se
 * fait à l'enregistrement, comme toute modification du formulaire, qui y vérifie encore ses règles.
 */
"use strict";
{
    const ROW = "tr.form-row:not(.empty-form)";

    // La rangée des refus d'une ligne, qui la précède (`admin/edit_inline/tabular.html`), ou null.
    const errorsOf = (row) => {
        const previous = row.previousElementSibling;
        return previous && previous.classList.contains("row-form-errors") ? previous : null;
    };

    // --- Tri ---

    let dragged = null;

    // Déplace `row` avant ou après `target`, avec la rangée de ses refus.
    const moveRow = (row, target, after) => {
        const errors = errorsOf(row);
        target[after ? "after" : "before"](row);
        if (errors) {
            row.before(errors);
        }
    };

    // Une ligne neuve dont aucun champ n'est rempli : Django l'ignore, sa position reste vide.
    const isBlank = (row) =>
        !row.classList.contains("has_original") &&
        ![...row.querySelectorAll("select, textarea, input:not([type=hidden])")].some(
            (field) => field.value,
        );

    // La poignée ne rend la ligne glissable que le temps d'un glisser.
    document.addEventListener("pointerdown", (event) => {
        const handle = event.target.closest(".sortable-handle");
        if (handle) {
            handle.closest("tr").draggable = true;
        }
    });

    document.addEventListener("dragstart", (event) => {
        const row = event.target.closest && event.target.closest(ROW);
        if (!row || !row.draggable) {
            return;
        }
        dragged = row;
        row.classList.add("sortable-dragging");
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", "");
    });

    document.addEventListener("dragover", (event) => {
        const target = dragged && event.target.closest && event.target.closest(ROW);
        if (!target || target === dragged || target.parentElement !== dragged.parentElement) {
            return;
        }
        event.preventDefault();
        const { top, height } = target.getBoundingClientRect();
        moveRow(dragged, target, event.clientY > top + height / 2);
    });

    document.addEventListener("drop", (event) => {
        if (dragged) {
            event.preventDefault();
        }
    });

    document.addEventListener("dragend", () => {
        if (dragged) {
            dragged.classList.remove("sortable-dragging");
            dragged.draggable = false;
            dragged = null;
        }
    });

    // Flèches haut et bas sur une poignée : la ligne monte ou descend d'un rang.
    document.addEventListener("keydown", (event) => {
        const handle = event.target.closest && event.target.closest(".sortable-handle");
        if (!handle || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) {
            return;
        }
        event.preventDefault();
        const row = handle.closest("tr");
        const rows = [...row.parentElement.querySelectorAll(ROW)].filter((line) => !line.hidden);
        const neighbour = rows[rows.indexOf(row) + (event.key === "ArrowUp" ? -1 : 1)];
        if (neighbour) {
            moveRow(row, neighbour, event.key === "ArrowDown");
            handle.focus();
        }
    });

    // À l'envoi, les positions suivent l'ordre affiché des lignes gardées et remplies.
    document.addEventListener("submit", (event) => {
        const bodies = new Set(
            [...event.target.querySelectorAll(".sortable-handle")].map((handle) =>
                handle.closest("tbody"),
            ),
        );
        bodies.forEach((body) => {
            let position = 0;
            body.querySelectorAll(ROW).forEach((row) => {
                const field = row.querySelector("input.sortable-position");
                if (field && !row.hidden && !isBlank(row)) {
                    position += 1;
                    field.value = `${position}`;
                }
            });
        });
    });

    // --- Suppression ---

    // Retire une ligne de l'écran, avec la rangée de ses refus.
    const hideRow = (row) => {
        row.hidden = true;
        const errors = errorsOf(row);
        if (errors) {
            errors.hidden = true;
        }
    };

    // Remplace la case par le bouton de Django. Sur un formulaire renvoyé en erreur, une ligne déjà
    // marquée pour suppression reste retirée de l'écran.
    const replaceCheckbox = (checkbox) => {
        const row = checkbox.closest("tr");
        const button = document.createElement("a");
        button.setAttribute("role", "button");
        button.href = "#";
        button.className = "inline-deletelink";
        button.textContent = window.gettext("Remove");
        button.addEventListener("click", (event) => {
            event.preventDefault();
            checkbox.checked = true;
            hideRow(row);
        });
        const wrapper = document.createElement("div");
        wrapper.append(button);
        checkbox.hidden = true;
        checkbox.after(wrapper);
        if (checkbox.checked) {
            hideRow(row);
        }
    };

    window.addEventListener("load", () => {
        document
            .querySelectorAll(".inline-group tr.has_original td.delete input[type=checkbox]")
            .forEach(replaceCheckbox);
    });
}
