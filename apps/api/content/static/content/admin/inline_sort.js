/*
 * Lignes en ligne de l'admin : les ordonner par glisser-déposer, avant l'enregistrement.
 *
 * Chaque ligne, enregistrée ou neuve, porte une poignée (`.sortable-handle`, posée par l'admin).
 * On fait glisser la ligne par sa poignée, ou on la déplace par les flèches haut et bas quand la
 * poignée a le focus. À l'envoi du formulaire, chaque ligne gardée reçoit sa position dans l'ordre
 * affiché, dans son champ caché (`.sortable-position`) ; une ligne neuve restée vide garde sa
 * position vide, pour que Django continue de l'ignorer. Glisser-déposer natif du navigateur, sans
 * bibliothèque (ADR 0013).
 *
 * Générique : vaut pour tout tableau en ligne de l'admin dont les lignes portent la poignée.
 */
"use strict";
{
    const ROW = "tr.form-row:not(.empty-form)";
    let dragged = null;

    // Déplace `row` avant ou après `target`, avec la rangée de ses refus, qui la précède.
    const moveRow = (row, target, after) => {
        const errors = row.previousElementSibling;
        target[after ? "after" : "before"](row);
        if (errors && errors.classList.contains("row-form-errors")) {
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

    const endDrag = () => {
        if (dragged) {
            dragged.classList.remove("sortable-dragging");
            dragged.draggable = false;
            dragged = null;
        }
    };
    document.addEventListener("dragend", endDrag);
    document.addEventListener("drop", (event) => {
        if (dragged) {
            event.preventDefault();
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

    // À l'envoi, les positions suivent l'ordre affiché des lignes gardées.
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
}
