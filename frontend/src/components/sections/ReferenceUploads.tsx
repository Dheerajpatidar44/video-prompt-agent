"use client";

import React from "react";
import { Users, Package, Building2 } from "lucide-react";
import { UploadCard } from "@/components/ui/UploadCard";

interface ReferenceUploadsProps {
  characterFiles: File[];
  productFiles: File[];
  brandFiles: File[];
  onCharacterFilesChange: (files: File[]) => void;
  onProductFilesChange: (files: File[]) => void;
  onBrandFilesChange: (files: File[]) => void;
}

export function ReferenceUploads({
  characterFiles,
  productFiles,
  brandFiles,
  onCharacterFilesChange,
  onProductFilesChange,
  onBrandFilesChange,
}: ReferenceUploadsProps) {
  return (
    <>
      <UploadCard
        label="Character References"
        description="Add images of characters, actors or models."
        icon={<Users size={16} />}
        files={characterFiles}
        onFilesChange={onCharacterFilesChange}
      />
      <UploadCard
        label="Product References"
        description="Add product images, packaging or assets."
        icon={<Package size={16} />}
        files={productFiles}
        onFilesChange={onProductFilesChange}
      />
      <UploadCard
        label="Brand / Company Assets"
        description="Upload your logo or brand assets."
        icon={<Building2 size={16} />}
        files={brandFiles}
        onFilesChange={onBrandFilesChange}
      />
    </>
  );
}
