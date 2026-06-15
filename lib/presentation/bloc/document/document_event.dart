      part of 'document_bloc.dart';

      abstract class DocumentEvent extends Equatable {
        const DocumentEvent();

        @override
        List<Object> get props => [];
      }

      class DocumentLoadEvent extends DocumentEvent {
        const DocumentLoadEvent();
      }

      class DocumentUploadEvent extends DocumentEvent {
        final File file;

        const DocumentUploadEvent({required this.file});

        @override
        List<Object> get props => [file];
      }

      class DocumentDeleteEvent extends DocumentEvent {
        final int documentId;

        const DocumentDeleteEvent({required this.documentId});

        @override
        List<Object> get props => [documentId];
      }