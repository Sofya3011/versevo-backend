// lib/presentation/bloc/document/document_bloc.dart
import 'dart:io';
import 'package:bloc/bloc.dart';
import 'package:equatable/equatable.dart';
import 'package:versevo_app/data/api/document_api.dart';
import 'package:versevo_app/data/models/document_model.dart';

part 'document_event.dart';
part 'document_state.dart';

class DocumentBloc extends Bloc<DocumentEvent, DocumentState> {
  final DocumentApi _documentApi = DocumentApi();

  DocumentBloc() : super(DocumentInitial()) {
    on<DocumentLoadEvent>(_onLoadDocuments);
    on<DocumentUploadEvent>(_onUploadDocument);
    on<DocumentDeleteEvent>(_onDeleteDocument);
  }

  Future<void> _onLoadDocuments(
      DocumentLoadEvent event,
      Emitter<DocumentState> emit,
      ) async {
    emit(DocumentLoading());
    try {
      final documents = await _documentApi.getDocuments();
      emit(DocumentLoaded(documents: documents));
    } catch (e) {
      emit(DocumentError(error: e.toString()));
    }
  }

  Future<void> _onUploadDocument(
      DocumentUploadEvent event,
      Emitter<DocumentState> emit,
      ) async {
    emit(DocumentLoading());
    try {
      final document = await _documentApi.uploadDocument(event.file);
      final currentState = state;
      if (currentState is DocumentLoaded) {
        emit(DocumentLoaded(documents: [...currentState.documents, document]));
      } else {
        emit(DocumentLoaded(documents: [document]));
      }
    } catch (e) {
      emit(DocumentError(error: e.toString()));
    }
  }

  Future<void> _onDeleteDocument(
      DocumentDeleteEvent event,
      Emitter<DocumentState> emit,
      ) async {
    emit(DocumentLoading());
    try {
      await _documentApi.deleteDocument(event.documentId);
      final currentState = state;
      if (currentState is DocumentLoaded) {
        final documents = currentState.documents
            .where((doc) => doc.id != event.documentId)
            .toList();
        emit(DocumentLoaded(documents: documents));
      }
    } catch (e) {
      emit(DocumentError(error: e.toString()));
    }
  }
}