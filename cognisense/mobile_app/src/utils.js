import { Alert } from 'react-native';

export function apiErrorMessage(e) {
  return e?.response?.data?.detail ?? e.message;
}

export function showApiError(e, title = 'Error') {
  Alert.alert(title, apiErrorMessage(e));
}
