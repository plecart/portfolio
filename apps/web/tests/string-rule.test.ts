/**
 * La règle des chaînes : aucun texte d'interface hors du catalogue `src/strings.ts` (spec §6.2 ;
 * brief de #18, décision 8 ; CONTRIBUTING.md, « Chaînes du front »).
 *
 * La porte est `no-restricted-syntax` d'ESLint sur `src/` : un texte qui contient une lettre,
 * écrit en dur là où l'interface le rend ou l'annonce.
 *
 * Dénombrement du 2026-10-08 : **12 formes** d'un texte d'interface écrit en dur dans un
 * composant, **6 couvertes** : texte JSX ; littéral entre accolades en enfant ; gabarit en enfant,
 * expressions comprises ; littéral dans un attribut annoncé ; littéral entre accolades dans un
 * attribut annoncé ; gabarit dans un attribut annoncé. Attributs annoncés : `aria-label`,
 * `aria-description`, `aria-roledescription`, `aria-valuetext`, `aria-placeholder`, `title`,
 * `alt`, `placeholder`, `label`. **6 hors portée**, à ne jamais supposer couvertes : une variable
 * ou une constante ; un littéral dans une expression (ternaire, `&&`, concaténation, appel) ; une
 * propriété de composant sous un autre nom (`content`, `text`) ; l'attribut `value`, rendu par un
 * bouton de formulaire mais donnée partout ailleurs ; un texte posé par le DOM (`textContent`,
 * `document.title`) ; les quatre balises du bloc d'aperçu d'`index.html`, du HTML statique
 * qu'ESLint ne lit pas — valeurs par défaut du site, que #14 remplace sur les fiches.
 *
 * Un texte sans lettre (« · », « — », « 3 ») passe : il n'a pas de langue.
 */
import { beforeAll, describe, expect, test } from 'vitest'
import { strings } from '../src/strings.ts'
import { LINT_WARM_UP_MS, lintComponent, warmUpLint } from './app-files.ts'

beforeAll(warmUpLint, LINT_WARM_UP_MS)

describe('ESLint refuse un texte d’interface en dur dans un composant', () => {
  test.each([
    ['texte JSX', '<p>Bonjour</p>'],
    ['texte JSX dans un fragment', '<>Bonjour</>'],
    ['lettre accentuée seule', '<p>à</p>'],
    ['capitale accentuée seule', '<p>À</p>'],
    ['littéral entre accolades en enfant', "<p>{'Bonjour'}</p>"],
    ['littéral entre accolades dans un fragment', "<>{'Bonjour'}</>"],
    ['gabarit en enfant', '<p>{`Bonjour`}</p>'],
    ['gabarit à expression en enfant', '<p>{`${count} projets`}</p>'],
    ['aria-label', '<button aria-label="Fermer" />'],
    ['aria-description', '<p aria-description="Résumé" />'],
    ['aria-roledescription', '<div aria-roledescription="carte" />'],
    ['aria-valuetext', '<div role="slider" aria-valuetext="moitié" />'],
    ['aria-placeholder', '<div role="textbox" aria-placeholder="Chercher" />'],
    ['title', '<abbr title="Interface" />'],
    ['alt', '<img alt="Photo" />'],
    ['placeholder', '<input placeholder="Chercher" />'],
    ['label', '<option label="Clair" />'],
    ['littéral entre accolades dans un attribut', "<button aria-label={'Fermer'} />"],
    ['gabarit dans un attribut', '<img alt={`Photo de ${name}`} />'],
  ])('%s', async (_, code) => {
    expect(await lintComponent(code)).toContain('no-restricted-syntax')
  })

  test.each([
    ['texte sans lettre', '<p>· — 3</p>'],
    ['chaîne du catalogue', '<p>{strings.siteName}</p>'],
    ['attribut non annoncé', '<a className="flex" href="/" id="nom" data-state="ouvert" />'],
    // Hors portée, dit dans l'en-tête : une expression n'est pas lue.
    ['ternaire', "<p>{open ? 'Ouvert' : 'Fermé'}</p>"],
    ['propriété de composant sous un autre nom', '<Tooltip content="Bonjour" />'],
  ])('%s passe', async (_, code) => {
    expect(await lintComponent(code)).not.toContain('no-restricted-syntax')
  })
})

test('aucune chaîne du catalogue ne porte d’apostrophe droite', () => {
  // Spec §6.2 : l'apostrophe typographique « ’ » dans les textes rendus.
  expect(Object.values(strings).filter((value) => value.includes("'"))).toEqual([])
})
