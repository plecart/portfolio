/*
 * Lignes des tableaux en ligne de l'admin : les ordonner et les supprimer avant l'enregistrement
 * (ADR 0013). Générique : vaut pour tout tableau en ligne dont l'écran charge ce script, ce que fait
 * `SortableInline` (`content/inlines.py`).
 *
 * Tri. Chaque ligne, enregistrée ou neuve, porte une poignée (`.sortable-handle`). On fait glisser
 * la ligne par sa poignée — glisser-déposer natif du navigateur, sans bibliothèque —, ou on la
 * déplace par les flèches haut et bas quand la poignée a le focus. À l'envoi du formulaire, chaque
 * ligne affichée reçoit sa position dans l'ordre affiché, dans son champ caché
 * (`.sortable-position`) ; le serveur ignore une ligne neuve dont seule la position est remplie
 * (`InlineRowForm.has_changed`). Quand l'écran revient en erreur, Django réaffiche les lignes dans
 * l'ordre de leurs index : le script les replace dans l'ordre de leurs positions.
 *
 * Index. Django lit une ligne enregistrée aux premiers index, autant qu'il y a de lignes
 * enregistrées, et une ligne neuve au-delà ; quand on retire une ligne neuve, il renumérote les
 * lignes dans l'ordre affiché (`admin/js/inlines.js`), et une ligne neuve glissée plus haut
 * prendrait l'index d'une ligne enregistrée. À l'envoi, le script renumérote les lignes
 * enregistrées d'abord, puis les neuves, chacune dans l'ordre affiché : les positions portent
 * l'ordre, les index n'en portent aucun.
 *
 * Suppression. Django donne à une ligne neuve un bouton qui la retire de l'écran, et à une ligne
 * enregistrée une case « Supprimer ? » (`admin/edit_inline/tabular.html`, `admin/js/inlines.js`).
 * La case est cachée et remplacée par le bouton de Django, même classe et même libellé (`deleteText`,
 * que Django pose dans la page) : un clic la coche — elle reste la donnée envoyée — et retire la
 * ligne de l'écran. La suppression en base se fait à l'enregistrement, comme toute modification du
 * formulaire, qui y vérifie encore ses règles.
 */
"use strict";
{
    const ROW = "tr.form-row:not(.empty-form)";

    // Les corps des tableaux ordonnables sous `root` : ceux dont les lignes portent une poignée.
    const sortableBodies = (root) =>
        new Set(
            [...root.querySelectorAll(".sortable-handle")].map((handle) => handle.closest("tbody")),
        );

    // Les options que Django pose sur le tableau en ligne d'un élément (`data-inline-formset`,
    // `admin/edit_inline/tabular.html`) : son préfixe, ses libellés.
    const formsetOptions = (element) =>
        JSON.parse(element.closest(".js-inline-admin-formset").dataset.inlineFormset).options;

    // La rangée des refus d'une ligne, qui la précède (`admin/edit_inline/tabular.html`), ou null.
    const errorsOf = (row) => {
        const previous = row.previousElementSibling;
        return previous && previous.classList.contains("row-form-errors") ? previous : null;
    };

    // --- Tri ---

    let dragged = null;

    // Déplace `row` avant ou après `target`, avec la rangée de ses refus ; placée avant `target`,
    // elle passe aussi avant la rangée des refus de `target`, qui reste collée à sa ligne.
    const moveRow = (row, target, after) => {
        const errors = errorsOf(row);
        if (after) {
            target.after(row);
        } else {
            (errorsOf(target) || target).before(row);
        }
        if (errors) {
            row.before(errors);
        }
    };

    // La poignée ne rend la ligne glissable que le temps d'un glisser : relâchée sans glisser, la
    // ligne ne l'est plus ; un glisser, lui, finit par `dragend`.
    let armed = null;
    document.addEventListener("pointerdown", (event) => {
        const handle = event.target.closest(".sortable-handle");
        if (handle) {
            armed = handle.closest("tr");
            armed.draggable = true;
        }
    });

    document.addEventListener("pointerup", () => {
        if (armed) {
            armed.draggable = false;
            armed = null;
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

    // Renumérote les lignes d'un corps, les enregistrées d'abord, puis les neuves, chacune dans
    // l'ordre affiché : même expression et mêmes attributs que Django (`updateElementIndex`).
    const renumber = (body) => {
        const { prefix } = formsetOptions(body);
        const pattern = new RegExp(`(${prefix}-(\\d+|__prefix__))`);
        const rows = [...body.querySelectorAll(ROW)];
        const saved = rows.filter((row) => row.classList.contains("has_original"));
        [...saved, ...rows.filter((row) => !saved.includes(row))].forEach((row, number) => {
            [row, ...row.querySelectorAll("*")].forEach((element) => {
                ["id", "name", "for"].forEach((attribute) => {
                    const value = element.getAttribute(attribute);
                    if (value) {
                        element.setAttribute(attribute, value.replace(pattern, `${prefix}-${number}`));
                    }
                });
            });
        });
    };

    // À l'envoi, les positions suivent l'ordre affiché des lignes gardées, puis les index sont
    // remis à la place où Django les lit.
    document.addEventListener("submit", (event) => {
        sortableBodies(event.target).forEach((body) => {
            let position = 0;
            body.querySelectorAll(ROW).forEach((row) => {
                const field = row.querySelector("input.sortable-position");
                if (field && !row.hidden) {
                    position += 1;
                    field.value = `${position}`;
                }
            });
            renumber(body);
        });
    });

    // Replace les lignes d'un corps dans l'ordre de leurs positions, celles qui n'en ont pas à la
    // fin, avec la rangée de leurs refus. Sur un écran renvoyé en erreur, l'ordre retrouve celui de
    // l'auteur ; sur un écran qui s'ouvre, les lignes suivent déjà l'ordre stocké.
    const sortRows = (body) => {
        const position = (row) =>
            Number(row.querySelector("input.sortable-position")?.value || Number.MAX_SAFE_INTEGER);
        const template = body.querySelector("tr.empty-form");
        [...body.querySelectorAll(ROW)]
            .map((row) => [errorsOf(row), row])
            .sort(([, a], [, b]) => position(a) - position(b))
            .forEach(([errors, row]) => {
                if (errors) {
                    body.insertBefore(errors, template);
                }
                body.insertBefore(row, template);
            });
    };

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
        // Le libellé que Django donne à ses propres boutons, traduit côté serveur : « Remove »
        // manque au catalogue JavaScript de l'admin, où `gettext` le laisserait en anglais.
        button.textContent = formsetOptions(checkbox).deleteText;
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
        sortableBodies(document).forEach(sortRows);
        document
            .querySelectorAll(".inline-group tr.has_original td.delete input[type=checkbox]")
            .forEach(replaceCheckbox);
    });
}
