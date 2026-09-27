/*
 * Lignes en ligne de l'admin : le même bouton de suppression pour toutes les lignes.
 *
 * Django donne à une ligne neuve un bouton qui la retire de l'écran, et à une ligne enregistrée une
 * case « Supprimer ? » (`admin/edit_inline/tabular.html`, `admin/js/inlines.js`). Ce script cache la
 * case et pose à sa place le bouton de Django, même classe et même libellé : un clic coche la case,
 * qui reste la donnée envoyée, et retire la ligne de l'écran. La suppression en base se fait à
 * l'enregistrement, comme toute modification du formulaire — et le formulaire y vérifie encore ses
 * règles, dont « au moins une technologie ».
 *
 * Générique : vaut pour tout tableau en ligne de l'admin dont l'écran charge ce script.
 */
"use strict";
{
    // Retire de l'écran la ligne de `checkbox`, et la rangée de ses refus qui la précède.
    const hideRow = (checkbox) => {
        const row = checkbox.closest("tr");
        row.hidden = true;
        const errors = row.previousElementSibling;
        if (errors && errors.classList.contains("row-form-errors")) {
            errors.hidden = true;
        }
    };

    // Remplace la case par le bouton de Django. Sur un formulaire renvoyé en erreur, une ligne déjà
    // marquée pour suppression reste retirée de l'écran.
    const replaceCheckbox = (checkbox) => {
        const button = document.createElement("a");
        button.setAttribute("role", "button");
        button.href = "#";
        button.className = "inline-deletelink";
        button.textContent = window.gettext("Remove");
        button.addEventListener("click", (event) => {
            event.preventDefault();
            checkbox.checked = true;
            hideRow(checkbox);
        });
        const wrapper = document.createElement("div");
        wrapper.append(button);
        checkbox.hidden = true;
        checkbox.after(wrapper);
        if (checkbox.checked) {
            hideRow(checkbox);
        }
    };

    window.addEventListener("load", () => {
        document
            .querySelectorAll(".inline-group tr.has_original td.delete input[type=checkbox]")
            .forEach(replaceCheckbox);
    });
}
