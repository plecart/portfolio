import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { slugFromPath } from './project/project.ts'
import './index.css'

// À l'adresse d'une fiche, la page naît « fiche ouverte » (spec §5.1) : l'entête et les liens de
// l'auteur prennent leur premier style déjà dans cet état, sans transition. `App` garde la main
// ensuite.
if (slugFromPath(location.pathname)) document.documentElement.setAttribute('data-project-open', '')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
