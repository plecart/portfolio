"""Les fichiers qu'une ligne de modèle nomme, et leur retrait du stockage quand elle ne les nomme
plus : la ligne supprimée, ou son fichier remplacé.

Django ne retire jamais un fichier du stockage, ni avec la ligne qui le nomme, ni quand un autre
fichier le remplace ; et le bucket est public (ADR 0004) : un fichier retiré resterait servi. Un
modèle qui hérite de `StoredFiles` dit seulement, champ par champ, ce qu'un nom retiré emporte
(`removals`) : le fichier seul (`delete_file_after_commit`) ou son dossier
(`delete_folder_after_commit`, `content/images.py`). Le reste est commun à tous les champs : le
suivi du nom que la ligne porte, la reconnaissance d'un remplacement et d'une suppression, et le
retrait, une fois la transaction validée, jamais si elle est annulée.

Un nom qu'une autre ligne du même modèle porte encore dans le même champ reste dans le stockage :
deux lignes peuvent nommer un même fichier — un nom affecté au champ, une ligne copiée. Le
stockage le rend rare sans l'exclure : un nom pris en rend un autre (`file_overwrite`,
`config/storage.py`).
"""

from collections.abc import Callable, Collection, Iterable, Mapping
from typing import TYPE_CHECKING, Any, ClassVar, Self

from django.core.files.storage import Storage
from django.db import models
from django.db.models.fields.files import FieldFile
from django.db.models.signals import pre_delete

from content.images import delete_after_commit

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.db.models.fetch_modes import FetchMode

# Ce qu'un nom retiré emporte : appelé avec le stockage du champ et le nom, il enregistre les
# suppressions à faire une fois la transaction validée.
Removal = Callable[[Storage, str], None]


def delete_file_after_commit(storage: Storage, name: str) -> None:
    """Supprime le seul fichier `name` de `storage` une fois la transaction en cours validée ;
    aucun si elle est annulée (`delete_after_commit`).

    Args:
        storage: le stockage qui tient le fichier.
        name: son nom de stockage.
    """
    delete_after_commit(storage, (name,))


class StoredFiles(models.Model):
    """Un modèle dont les fichiers sortent du stockage quand la ligne ne les nomme plus.

    Chaque modèle concret qui en hérite nomme ses champs fichier dans `removals`, avec ce qu'un nom
    retiré emporte. Un nom est retiré quand la ligne qui le portait est supprimée — seule, ou par
    une cascade : Django envoie `pre_delete` pour chaque ligne qu'elle emporte —, ou quand un
    enregistrement en écrit un autre dans le champ. Le retrait part une fois la transaction
    validée, jamais si elle est annulée, et une panne du stockage n'y fait pas échouer la requête
    qui a validé (`delete_after_commit`).

    Une suppression que Django refuse — une ligne protégée (`PROTECT`) — ne retire rien : le refus
    tombe au recensement des lignes (`Collector.collect`), avant tout signal
    (`Collector.delete`).
    """

    # Chaque champ fichier du modèle, et ce qu'un nom retiré y emporte.
    removals: ClassVar[Mapping[str, Removal]]

    # Le nom que la ligne portait, champ par champ, quand cette instance l'a lu ou écrit pour la
    # dernière fois : ce qu'elle-même change, et rien d'autre (`_replaced_name`). Un champ absent
    # est un nom que l'instance ignore. Jamais modifié en place : remplacé.
    _stored_names: Mapping[str, str | None] = {}

    class Meta:
        abstract = True

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Chaque modèle qui hérite du mécanisme reçoit la suppression de ses lignes : branchée sur
        lui seul (`sender`), et non sur tous les modèles — un récepteur sans expéditeur ôterait à
        chacun la suppression directe par une seule requête (`Collector.can_fast_delete`)."""
        super().__init_subclass__(**kwargs)
        pre_delete.connect(cls._remove_deleted_files, sender=cls)

    @classmethod
    def from_db(
        cls,
        db: str | None,
        field_names: Collection[str],
        values: Collection[Any],
        *,
        fetch_mode: "FetchMode | None" = None,
    ) -> Self:
        """La ligne lue, qui retient le nom de chaque fichier chargé (doc Django, « Customizing
        model loading »)."""
        instance = super().from_db(db, field_names, values, fetch_mode=fetch_mode)
        instance._remember(field for field in cls.removals if field in field_names)
        return instance

    def refresh_from_db(
        self,
        using: str | None = None,
        fields: Iterable[str] | None = None,
        from_queryset: "QuerySet[Any] | None" = None,
    ) -> None:
        """La ligne relue, qui retient le nom de chaque fichier relu — le chargement à la demande
        d'un champ différé passe par ici (`DeferredAttribute`).

        Args:
            using, fields, from_queryset: ceux de `Model.refresh_from_db`.
        """
        fields = None if fields is None else set(fields)
        deferred = self.get_deferred_fields()
        reloaded = [
            field
            for field in self.removals
            if (field not in deferred if fields is None else field in fields)
        ]
        super().refresh_from_db(using=using, fields=fields, from_queryset=from_queryset)
        self._remember(reloaded)

    def save(self, **kwargs: Any) -> None:
        """Enregistre la ligne ; un fichier remplacé sort du stockage une fois la transaction
        validée.

        Un enregistrement partiel (`update_fields`) ne remplace que les fichiers qu'il écrit.

        Args:
            kwargs: ceux de `Model.save`.
        """
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            # Un itérable quelconque, que Django relira : lu une fois ici, gardé en ensemble.
            update_fields = kwargs["update_fields"] = frozenset(update_fields)
        replaced = {
            field: name
            for field in self._written(update_fields)
            if (name := self._replaced_name(field))
        }
        self.save_replacing(replaced, **kwargs)

    def save_replacing(self, replaced: Mapping[str, str], **kwargs: Any) -> None:
        """Écrit la ligne, qui ne nomme plus les fichiers `replaced`, puis enregistre leur retrait.

        Le point d'extension d'un modèle que le remplacement d'un fichier concerne : il connaît ici
        ce que l'écriture remplace, avant et après elle.

        Args:
            replaced: chaque champ dont l'écriture remplace le fichier, et le nom que la ligne
                portait.
            kwargs: ceux de `Model.save` ; `update_fields`, s'il y est, est un ensemble.
        """
        super().save(**kwargs)
        self._remember(self._written(kwargs.get("update_fields")))
        for field, name in replaced.items():
            self._remove(field, name)

    def _written(self, update_fields: Collection[str] | None) -> list[str]:
        """Les champs fichier qu'un enregistrement de `update_fields` écrit — tous sans eux."""
        return [field for field in self.removals if update_fields is None or field in update_fields]

    def _file(self, field: str) -> FieldFile:
        """Le fichier que l'instance tient dans `field`."""
        file: FieldFile = getattr(self, field)
        return file

    def _remember(self, fields: Iterable[str]) -> None:
        """Retient le nom que l'instance tient dans chacun de `fields` : celui que la ligne porte."""
        self._stored_names = {
            **self._stored_names,
            **{field: self._file(field).name for field in fields},
        }

    def _replaced_name(self, field: str) -> str | None:
        """Le nom que la ligne porte dans `field` et que cette instance remplace en s'enregistrant ;
        aucun pour une ligne neuve, ou dont cette instance n'a pas changé le fichier.

        Un téléversement affecté au champ remplace toujours : ce que la ligne nomme au moment de
        l'écriture ne l'est plus après, quoi que l'instance ait lu. Un nom déjà stocké ne remplace
        que si l'instance sait lequel elle a lu ou écrit, et l'a changé — un fichier enregistré par
        `FieldFile.save`, un nom affecté ; une instance qui ignore ce nom — son fichier chargé avec
        ses pairs (`FETCH_PEERS`), sans passer par `refresh_from_db` — ne retire rien. La ligne est
        relue, jamais le fichier, et son nom n'est retiré que s'il n'est pas ce que l'instance
        écrit.
        """
        if self._state.adding:
            return None
        file = self._file(field)
        # `_committed`, posé par `FieldFile` : faux pour un téléversement à enregistrer — le concept
        # d'`OriginalFile.stored` (`content/images.py`).
        uploading = bool(file) and not getattr(file, "_committed", True)
        known = self._stored_names.get(field)
        if not uploading and (known is None or file.name == known):
            return None
        row = type(self)._base_manager.only(field).filter(pk=self.pk).first()
        name = None if row is None else row._file(field).name
        return name if name and name != file.name else None

    def _remove(self, field: str, name: str) -> None:
        """Retire `name`, que la ligne ne nomme plus dans `field`, par ce que `removals` lui donne
        — sauf si une autre ligne du même modèle le porte encore dans ce champ."""
        model = type(self)
        if model._base_manager.filter(**{field: name}).exclude(pk=self.pk).exists():
            return
        model.removals[field](self._file(field).storage, name)

    @staticmethod
    def _remove_deleted_files(
        sender: type["StoredFiles"], instance: "StoredFiles", **kwargs: object
    ) -> None:
        """Les fichiers d'une ligne supprimée sortent du stockage une fois la transaction validée.

        Ses noms se lisent dans la ligne, avant sa suppression : pas dans l'instance, qui peut tenir
        un fichier remplacé en mémoire, des valeurs périmées ou différées (`only`).

        Args:
            sender: le modèle de la ligne.
            instance: la ligne supprimée.
            kwargs: le reste du signal.
        """
        # ponytail: une lecture par ligne supprimée, cascades comprises, et une par nom retiré —
        # une galerie compte quelques images ; si elles se comptent par centaines, lire les noms
        # d'un coup au `pre_delete` du projet. Deux lignes qui nomment un même fichier, supprimées
        # ensemble, le gardent : chacune voit l'autre encore là.
        row = sender._base_manager.only(*sender.removals).filter(pk=instance.pk).first()
        if row is None:
            return
        for field in sender.removals:
            if name := row._file(field).name:
                row._remove(field, name)
