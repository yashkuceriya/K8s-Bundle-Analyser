import axios from 'axios';
import type { BundleInfo, AnalysisResult, ChatRequest, ChatResponse, AnalysisHistoryEntry, CompareRequest, CompareResponse } from '../types';

const api = axios.create({
  baseURL: '/api',
});

export async function uploadBundle(file: File): Promise<BundleInfo> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post<BundleInfo>('/bundles/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

export async function getBundles(): Promise<BundleInfo[]> {
  const response = await api.get<BundleInfo[]>('/bundles/');
  return response.data;
}

export async function getBundle(id: string): Promise<BundleInfo> {
  const response = await api.get<BundleInfo>(`/bundles/${id}`);
  return response.data;
}

export async function analyzeBundle(id: string): Promise<AnalysisResult> {
  const response = await api.post<AnalysisResult>(`/bundles/${id}/analyze`);
  return response.data;
}

export async function getAnalysis(id: string): Promise<AnalysisResult> {
  const response = await api.get<AnalysisResult>(`/bundles/${id}/analysis`);
  return response.data;
}

export async function deleteBundle(id: string): Promise<void> {
  await api.delete(`/bundles/${id}`);
}

export async function reanalyzeBundle(id: string): Promise<AnalysisResult> {
  const response = await api.post<AnalysisResult>(`/bundles/${id}/reanalyze`);
  return response.data;
}

export async function exportReport(id: string): Promise<Blob> {
  const response = await api.get(`/bundles/${id}/export`, { responseType: 'blob' });
  return response.data;
}

export async function getPreflightSpec(id: string): Promise<string> {
  const response = await api.get(`/bundles/${id}/preflight`, { responseType: 'text' });
  return response.data;
}

export async function chatWithBundle(id: string, request: ChatRequest): Promise<ChatResponse> {
  const response = await api.post<ChatResponse>(`/bundles/${id}/chat`, request);
  return response.data;
}

export async function getAnalysisHistory(id: string): Promise<AnalysisHistoryEntry[]> {
  const response = await api.get<AnalysisHistoryEntry[]>(`/bundles/${id}/history`);
  return response.data;
}

export async function getHistoricalAnalysis(id: string, timestamp: string): Promise<AnalysisResult> {
  const response = await api.get<AnalysisResult>(`/bundles/${id}/history/${timestamp}`);
  return response.data;
}

export async function compareAnalyses(request: CompareRequest): Promise<CompareResponse> {
  const response = await api.post<CompareResponse>('/bundles/compare', request);
  return response.data;
}
