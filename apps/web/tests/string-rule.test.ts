/**
 * La règle des chaînes : aucun texte d'interface hors du catalogue `src/strings.ts` (spec §6.2 ;
 * brief de #18, décision 8 ; CONTRIBUTING.md, « Chaînes du front »).
 *
 * La porte est `no-restricted-syntax` d'ESLint sur `src/` : un texte qui contient une lettre,
 * écrit en dur là où l'interface le rend ou l'annonce.
 *
 * Dénombrement du 2026-10-08, repris à la première relecture : **17 formes** d'un texte
 * d'interface écrit en dur dans ce front, **6 couvertes** — texte JSX ; littéral entre accolades
 * en enfant ; gabarit en enfant, expressions comprises ; littéral dans un attribut annoncé ;
 * littéral entre accolades dans un attribut annoncé ; gabarit dans un attribut annoncé —, enfant
 * d'un élément ou d'un fragment. Attributs annoncés : `aria-label`, `aria-description`,
 * `aria-roledescription`, `aria-braillelabel`, `aria-brailleroledescription`, `aria-valuetext`,
 * `aria-placeholder`, `title`, `alt`, `abbr`, `placeholder`, `label`.
 *
 * **11 hors portée**, à ne jamais supposer couvertes — chacune épinglée ci-dessous par un cas qui
 * passe, sauf les deux qu'ESLint ne lit pas : une variable ou une constante ; un littéral dans une
 * expression (ternaire, `&&`, concaténation, appel, assertion `as`) ; une propriété de composant
 * sous un autre nom (`content`, `text`) ; un attribut passé par décomposition (`{...props}`) ;
 * l'attribut `value`, rendu par un bouton de formulaire mais donnée partout ailleurs ; du HTML
 * passé à `dangerouslySetInnerHTML` ; un texte produit par CSS dans une classe
 * (`before:content-['…']`) ; une balise `<meta>` posée en JSX, que React remonte dans `<head>` ;
 * un texte posé par le DOM (`textContent`, `document.title`). Hors d'ESLint : un texte produit par
 * CSS dans une feuille (`content: "…"`) ; les quatre balises du bloc d'aperçu d'`index.html` —
 * valeurs par défaut du site, que #14 remplace sur les fiches.
 *
 * Un texte sans lettre (« · », « — », « 3 ») passe : il n'a pas de langue.
 */
import { beforeAll, describe, expect, test } from 'vitest'
import { strings } from '../src/strings.ts'
import { LINT_WARM_UP_MS, lintComponent, warmUpLint } from './app-files.ts'

beforeAll(warmUpLint, LINT_WARM_UP_MS)

/** Le refus de cette règle, et pas celui de la règle des valeurs, qui partage son identifiant. */
const STRING_REFUSAL = expect.stringContaining("Texte d'interface en dur")

describe('ESLint refuse un texte d’interface en dur dans un composant', () => {
  test.each([
    ['texte JSX', '<p>Bonjour</p>'],
    ['texte JSX dans un fragment', '<>Bonjour</>'],
    ['lettre accentuée seule', '<p>à</p>'],
    ['capitale accentuée seule', '<p>À</p>'],
    ['littéral entre accolades en enfant', "<p>{'Bonjour'}</p>"],
    ['littéral entre accolades dans un fragment', "<>{'Bonjour'}</>"],
    ['gabarit en enfant', '<p>{`Bonjour`}</p>'],
    ['gabarit dans un fragment', '<>{`Bonjour`}</>'],
    ['gabarit à expression en enfant', '<p>{`${count} projets`}</p>'],
    ['aria-label', '<button aria-label="Fermer" />'],
    ['aria-description', '<p aria-description="Résumé" />'],
    ['aria-roledescription', '<div aria-roledescription="carte" />'],
    ['aria-braillelabel', '<button aria-braillelabel="Fermer" />'],
    ['aria-brailleroledescription', '<div aria-brailleroledescription="carte" />'],
    ['aria-valuetext', '<div role="slider" aria-valuetext="moitié" />'],
    ['aria-placeholder', '<div role="textbox" aria-placeholder="Chercher" />'],
    ['title', '<abbr title="Interface" />'],
    ['alt', '<img alt="Photo" />'],
    ['abbr', '<th abbr="Nombre" />'],
    ['placeholder', '<input placeholder="Chercher" />'],
    ['label', '<option label="Clair" />'],
    ['littéral entre accolades dans un attribut', "<button aria-label={'Fermer'} />"],
    ['gabarit dans un attribut', '<img alt={`Photo de ${name}`} />'],
  ])('%s', async (_, code) => {
    expect(await lintComponent(code)).toContainEqual(STRING_REFUSAL)
  })

  test.each([
    ['texte sans lettre', '<p>· — 3</p>'],
    ['chaîne du catalogue', '<p>{strings.siteName}</p>'],
    ['attribut non annoncé', '<a className="flex" href="/" id="nom" data-state="ouvert" />'],
    ['attribut au nom voisin d’un annoncé', '<p aria-labelledby="titre" data-title="nom" />'],
    // Hors portée, dits dans l'en-tête.
    ['variable', '<p>{label}</p>'],
    ['ternaire', "<p>{open ? 'Ouvert' : 'Fermé'}</p>"],
    ['assertion as', "<p>{'Bonjour' as const}</p>"],
    ['propriété de composant sous un autre nom', '<Tooltip content="Bonjour" />'],
    ['décomposition', "<button {...{ 'aria-label': 'Fermer' }} />"],
    ['value', '<input type="submit" value="Envoyer" />'],
    ['dangerouslySetInnerHTML', "<p dangerouslySetInnerHTML={{ __html: 'Bonjour' }} />"],
    ['texte produit par CSS', '<p className="before:content-[\'Nouveau\']" />'],
    ['balise meta en JSX', '<meta name="description" content="Portfolio de Pacôme" />'],
    ['texte posé par le DOM', "document.title = 'Pacôme Bernier'"],
  ])('%s passe', async (_, code) => {
    expect(await lintComponent(code)).not.toContainEqual(STRING_REFUSAL)
  })
})

test('aucune chaîne du catalogue ne porte d’apostrophe droite', () => {
  // Spec §6.2 : l'apostrophe typographique « ’ » dans les textes rendus.
  expect(Object.values(strings).filter((value) => value.includes("'"))).toEqual([])
})
