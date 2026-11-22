export interface AppConfig {
  /** URL du backend FastAPI (voir le contrat d'API du plan). */
  apiUrl: string;
  /**
   * true  : tout est simulé dans le navigateur (aucun serveur nécessaire).
   * false : les appels partent vers `apiUrl`.
   */
  useMock: boolean;
}

export const APP_CONFIG: AppConfig = {
  apiUrl: 'http://localhost:8000',
  useMock: false,
};
