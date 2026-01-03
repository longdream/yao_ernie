import React, { useRef, useState } from 'react'
import type { ImageAttachment } from '../utils/types'

interface ImageUploadProps {
  images: ImageAttachment[]
  onImagesChange: (images: ImageAttachment[]) => void
  maxImages?: number
  maxSize?: number // in bytes
  disabled?: boolean
}

export const ImageUpload: React.FC<ImageUploadProps> = ({
  images,
  onImagesChange,
  maxImages = 5,
  maxSize = 10 * 1024 * 1024, // 10MB
  disabled = false
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || disabled) return

    const validFiles: File[] = []
    const errors: string[] = []

    // 验证文件
    Array.from(files).forEach(file => {
      // 检查文件类型
      if (!file.type.startsWith('image/')) {
        errors.push(`${file.name}: 不是有效的图片文件`)
        return
      }

      // 检查文件大小
      if (file.size > maxSize) {
        errors.push(`${file.name}: 文件大小超过${Math.round(maxSize / 1024 / 1024)}MB`)
        return
      }

      // 检查数量限制
      if (images.length + validFiles.length >= maxImages) {
        errors.push(`最多只能上传${maxImages}张图片`)
        return
      }

      validFiles.push(file)
    })

    // 显示错误信息
    if (errors.length > 0) {
      console.warn('图片上传错误:', errors)
      // 这里可以添加toast提示
    }

    // 处理有效文件
    const newImages: ImageAttachment[] = []
    for (const file of validFiles) {
      try {
        const base64 = await fileToBase64(file)
        const imageAttachment: ImageAttachment = {
          id: `img_${Date.now()}_${Math.random().toString(36).slice(2)}`,
          name: file.name,
          url: URL.createObjectURL(file),
          base64: base64,
          mimeType: file.type,
          size: file.size
        }
        newImages.push(imageAttachment)
      } catch (error) {
        console.error(`Failed to process ${file.name}:`, error)
      }
    }

    if (newImages.length > 0) {
      onImagesChange([...images, ...newImages])
    }
  }

  const fileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => {
        const result = reader.result as string
        // 移除data:image/jpeg;base64,前缀，只保留base64数据
        const base64 = result.split(',')[1]
        resolve(base64)
      }
      reader.onerror = reject
      reader.readAsDataURL(file)
    })
  }

  const removeImage = (imageId: string) => {
    const updatedImages = images.filter(img => {
      if (img.id === imageId) {
        // 清理URL对象
        URL.revokeObjectURL(img.url)
        return false
      }
      return true
    })
    onImagesChange(updatedImages)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    if (!disabled) {
      setDragOver(true)
    }
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (!disabled) {
      handleFileSelect(e.dataTransfer.files)
    }
  }

  const handleClick = () => {
    if (!disabled && fileInputRef.current) {
      fileInputRef.current.click()
    }
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes}B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
    return `${(bytes / 1024 / 1024).toFixed(1)}MB`
  }

  return (
    <div className="space-y-3">
      {/* 上传区域 */}
      <div
        className={`
          border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors
          ${dragOver ? 'border-gray-400 bg-gray-50' : 'border-gray-300 hover:border-gray-400'}
          ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
        `}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => handleFileSelect(e.target.files)}
          disabled={disabled}
        />
        
        <div className="flex flex-col items-center gap-2">
          <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          <div className="text-sm text-gray-600">
            <span className="font-medium text-gray-600">点击上传</span> 或拖拽图片到此处
          </div>
          <div className="text-xs text-gray-500">
            支持 JPG、PNG、GIF 格式，最大{Math.round(maxSize / 1024 / 1024)}MB，最多{maxImages}张
          </div>
        </div>
      </div>

      {/* 已上传的图片列表 */}
      {images.length > 0 && (
        <div className="space-y-2">
          <div className="text-sm font-medium text-gray-700">已选择的图片 ({images.length})</div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {images.map((image) => (
              <div key={image.id} className="relative group">
                <div className="aspect-square rounded-lg overflow-hidden bg-gray-100">
                  <img
                    src={image.url}
                    alt={image.name}
                    className="w-full h-full object-cover"
                  />
                </div>
                
                {/* 删除按钮 */}
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    removeImage(image.id)
                  }}
                  className="absolute -top-2 -right-2 w-6 h-6 bg-red-500 text-white rounded-full flex items-center justify-center text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                  disabled={disabled}
                >
                  ×
                </button>
                
                {/* 文件信息 */}
                <div className="mt-1 text-xs text-gray-500 truncate">
                  <div className="truncate">{image.name}</div>
                  <div>{formatFileSize(image.size)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
