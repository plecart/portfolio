/**
 * Généré depuis apps/api/openapi.json par `make web-openapi` : ne pas éditer.
 */

export interface paths {
    "/api/projets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Projects
         * @description `GET /api/projets` : la liste nue des projets publiés, `[]` s'il n'y en a aucun.
         *
         *     Sans cookie. `Cache-Control: no-cache` et `ETag` : la réponse se revalide à chaque visite par
         *     `If-None-Match`, `304` tant que rien n'a changé.
         */
        get: operations["content_api_projects"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * GalleryImageOut
         * @description Une image de la galerie. Une image en attente ou en échec est exposée avec son état et
         *     sans variante (décision 4) : le front décide ce qu'il dessine.
         */
        GalleryImageOut: {
            /** Caption */
            caption: string;
            /** Width */
            width: number;
            /** Height */
            height: number;
            state: components["schemas"]["ProcessingState"];
            /** Variants */
            variants: components["schemas"]["VariantOut"][];
        };
        /**
         * ProcessingState
         * @description L'état de traitement d'une image : le worker de #12 la convertit et en produit les
         *     variantes. Valeurs stockées en anglais, exposées telles quelles par l'API (ADR 0010) ; au
         *     niveau du module pour la même raison que `TechnologyKind`.
         * @enum {string}
         */
        ProcessingState: "pending" | "ready" | "failed";
        /**
         * ProjectKind
         * @description Le type d'un projet. Valeurs stockées en anglais, exposées telles quelles par l'API
         *     (ADR 0010) ; au niveau du module pour la même raison que `TechnologyKind`.
         * @enum {string}
         */
        ProjectKind: "personal" | "professional" | "school";
        /**
         * ProjectOut
         * @description Un projet publié, complet : ses faits, ses technologies, sa galerie — dont la première
         *     image est la couverture — et les sections de sa fiche, chaque liste dans l'ordre de l'admin.
         *
         *     `finished_on` vaut `null` tant que le projet est en cours ; un lien absent est une chaîne
         *     vide, comme stocké.
         */
        ProjectOut: {
            /** Slug */
            slug: string;
            /** Title */
            title: string;
            /** Summary */
            summary: string;
            /** Description */
            description: string;
            kind: components["schemas"]["ProjectKind"];
            status: components["schemas"]["ProjectStatus"];
            /**
             * Started On
             * Format: date
             */
            started_on: string;
            /** Finished On */
            finished_on: string | null;
            /** Client */
            client: string;
            /** Repository Url */
            repository_url: string;
            /** Demo Url */
            demo_url: string;
            /** Showcase */
            showcase: boolean;
            /** Technologies */
            technologies: components["schemas"]["TechnologyOut"][];
            /** Gallery */
            gallery: components["schemas"]["GalleryImageOut"][];
            /** Sections */
            sections: components["schemas"]["SectionOut"][];
        };
        /**
         * ProjectStatus
         * @description Le statut d'un projet. Valeurs stockées en anglais, exposées telles quelles par l'API
         *     (ADR 0010) ; au niveau du module pour la même raison que `TechnologyKind`.
         * @enum {string}
         */
        ProjectStatus: "ongoing" | "finished" | "archived";
        /**
         * SectionOut
         * @description Une section de la fiche technique : titre, ancre et corps Markdown.
         */
        SectionOut: {
            /** Title */
            title: string;
            /** Anchor */
            anchor: string;
            /** Body */
            body: string;
        };
        /**
         * TechnologyKind
         * @description Le type d'une technologie. Valeurs stockées en anglais, exposées telles quelles par l'API
         *     (ADR 0010).
         *
         *     Au niveau du module, et non dans `Technology` : la contrainte de `Meta` qui borne le type à
         *     ces valeurs ne voit pas les noms du corps de la classe qui l'entoure.
         * @enum {string}
         */
        TechnologyKind: "language" | "framework" | "infrastructure" | "tool";
        /**
         * TechnologyOut
         * @description Une technologie qu'un projet emploie : son nom, son type et l'adresse de son icône SVG,
         *     que le site charge en `<img>` (décision 5) — jamais le SVG lui-même.
         */
        TechnologyOut: {
            /** Name */
            name: string;
            kind: components["schemas"]["TechnologyKind"];
            /** Icon */
            icon: string;
        };
        /**
         * VariantOut
         * @description Une variante d'une image prête : son adresse à la place de son nom de stockage.
         */
        VariantOut: {
            /** Url */
            url: string;
            /** Width */
            width: number;
            /** Height */
            height: number;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    content_api_projects: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description OK */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"][];
                };
            };
        };
    };
}
