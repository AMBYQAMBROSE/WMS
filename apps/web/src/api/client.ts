import axios from "axios";

import { useAuthStore } from "@/stores/authStore";

export const apiClient = axios.create({
  baseURL: "/api/v1",
  // Send array parameters as ids=a&ids=b (FastAPI's format) instead of axios's default ids[]=a
  paramsSerializer: { indexes: null },
});

apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
    }
    return Promise.reject(error);
  }
);
