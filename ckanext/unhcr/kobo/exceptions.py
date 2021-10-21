class KoboApiError(Exception):
    pass


class KoBoDuplicatedDatasetError(Exception):
    pass


class KoboMissingAssetIdError(Exception):
    pass


class KoBoSurveyError(Exception):
    pass


class KoBoEmptySurveyError(Exception):
    pass


class KoBoUserTokenMissingError(Exception):
    pass
