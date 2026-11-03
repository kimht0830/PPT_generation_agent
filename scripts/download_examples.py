"""논문(paper.pdf) - 발표 슬라이드(slides.pdf) 쌍을 examples/ 폴더로 다운로드한다.

사용법:
    python scripts/download_examples.py            # 전체
    python scripts/download_examples.py --limit 3  # 앞의 3개만 (테스트)

폴더 구조:
    examples/<CONF><YEAR>_<key>/paper.pdf
    examples/<CONF><YEAR>_<key>/slides.pdf
    examples/manifest.json   (원본 메타데이터 + 정규화한 PDF URL + 다운로드 상태)
"""
import argparse
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "examples"

# ---------------------------------------------------------------------------
# 데이터: (conference, year) -> {key: paper_id}
#   ECCV      : paper_id = 5자리 번호
#   ICLR/ICML2025 : paper_id = OpenReview forum id
#   CVPR      : paper_id = *_paper 파일명 (확장자 제외)
#   ICML2023/24   : paper_id = PMLR 약칭 (예: liu23e)
# ---------------------------------------------------------------------------
DATA = {
    ("ECCV", "2024"): {
        "1041": "04761", "1112_AVIlFBK": "09400", "1187": "03461", "1227": "02444",
        "1349_WHtPdnV": "05636", "1386": "00633", "1498": "06579", "179": "01421",
        "1823": "07629", "1929": "05600", "1979": "10038", "2449_sTmyroP": "02513",
        "2582_a9p6nLs": "05758", "2600": "08278", "2605": "08759", "2625_tk2zgNa": "09204",
        "330": "11182", "728_gee7MLG": "07783", "744": "04155", "816": "12401",
        "823": "11332", "867_Q6p1jL2": "05502",
    },
    ("ICLR", "2024"): {
        "17587": "u7559ZMvwY", "17596": "ttXg3SKAg5", "17691": "rTDyN8yajn",
        "17742": "qDdSRaOiyb", "17965": "kklwv4c4dI", "17973": "kUCgHbmO11",
        "18303_as9utA5": "cH3oufN8Pl", "18419": "YbZxT0SON4", "18719": "P1aobHnjjj",
        "18749": "OGtnhKQJms", "18794": "NG7sS51zVF", "18856": "LebzzClHYw",
        "18911": "KI9NqjLVDT", "18991": "HXWTXXtHNl", "19176": "CNL2bku4ra",
        "19267": "AJBkfwXh3u", "19274": "A4mJuFRMN8", "19357_MGj1Or1": "7VPTUWkiDQ",
        "19410": "5t44vPlv9x", "19438": "5BCFlnfE1g", "19450": "4iPw1klFWa",
        "19484": "3zKtaqxLhW", "19515": "3QLkwU40EE", "19562": "22OTbutug9",
        "19613": "0akLDTFR9x",
    },
    ("ICLR", "2025"): {
        "27652": "zl0HLZOJC9", "27709": "ydlDRUuGm9", "27715": "yaQbTAD2JJ",
        "27766": "xkgfLXZ4e0", "27896": "vi3DjUhFVm", "27933": "v6iLQBoIJw",
        "27934_sDLZNv7": "v593OaNePQ", "27947": "uuriavczkL", "27948": "uuef1HP6X7",
        "27997_fkEhnBT": "uAFHCZRmXk", "28038_pShxFVe": "te2IdORabL", "28082": "szRmEM8Kx5",
        "28088": "swWF948IiC", "28103": "si37wk8U5D", "28184_NKKXsTr": "rdSVgnLHQB",
        "28206": "rGyi8NNqB0", "28215": "rAoEub6Nw2", "28252": "qNp86ByQlN",
        "28282_VHNBZL6": "plgLA2YBLH", "28284": "peX9zpWgg4", "28293": "pXN8T5RwNN",
        "28308": "pH543jrbe8", "28333": "onIro14tHv", "28366_bABHyUT": "oI5tZaWkF9",
        "28394": "nobDw4d1k7", "28467_LEQRMgp": "mP7uV59iJM", "28494": "ltrxRX5t0H",
        "28546": "l0ZzTvPfTw", "28561": "kmgrlG9TR0", "28615": "jqVj8vCQsT",
        "28638": "jTEKTdI3K9", "28703": "iGbuc9ekKK", "28890_MPgOse9": "f9w89OY2cp",
        "28984": "dSneEp59yX", "29008": "d63a4AM4hb", "29010_i1dysCC": "d54fIsAbff",
        "29060": "cJPUpL8mOw", "29209": "ZbkqhKbggH", "29225": "ZJftXKy12x",
        "29231": "ZCOwwRAaEl", "29390": "VxvnV6slP0", "29399": "VoayJihXra",
        "29438": "UxkznlcnHf", "29446": "UstOpZCESc", "29456": "UnCKU8pZVe",
        "29483": "UGVYezlLcZ", "29610": "SOd07Qxkw4", "29668_X3fGnVg": "QzPKSUUcud",
        "29718": "Q0TEVKV2cp", "29770": "P8pqeEkn1H", "29808": "OhauMUNW8T",
        "29810": "Oh8MuCacJW", "29832_DX1YZBv": "OIvg3MqWX2", "29919_9O41nW5": "Mn2qgIcIPS",
        "29971": "LuT2CVrlpU", "29997": "LRrbD8EZJl", "30041": "KeRwLLwZaw",
        "30077": "K3n5jPkrU6", "30145_zl0EZC4": "Iu8FVcUmVp", "30196": "I0n3EyogMi",
        "30235": "HF1UmIVv6a", "30448": "DhH3LbA6F6", "30465": "DKkQtRMowq",
        "30496": "Cnwz9jONi5", "30542_pE26Ek0": "BpyHIrpUOL", "30568": "BWS5gVjgeY",
        "30748": "8jvVNPHtVJ", "30795": "7uDI7w5RQA", "30804": "7lpDn2MhM2",
        "30860": "6s5uXNWGIh", "30862": "6p74UyAdLa", "30894": "6Mg7pjG7Sw",
        "31025": "4FVGowGzQb", "31103": "2vgcDW2blS", "31115": "2p03KljxE9",
        "31140": "2PzozgigiA", "31174_XwCr9VL": "1vrpdV9U3i", "31215": "1F8xTfv6ah",
        "31238": "0nJEgNpb4l", "31262": "0FxnSZJPmh", "32087": "QG31By6S6w",
        "32097_E7F3kpW": "JXgnnUC0PH",
    },
    ("CVPR", "2023"): {
        "20941_8wm5267": "Yu_Hint-Aug_Drawing_Hints_From_Foundation_Vision_Transformers_Towards_Boosted_Few-Shot_CVPR_2023_paper",
        "20951": "Chen_Learning_a_Deep_Color_Difference_Metric_for_Photographic_Images_CVPR_2023_paper",
        "20978": "Cha_Learning_To_Generate_Text-Grounded_Mask_for_Open-World_Semantic_Segmentation_From_CVPR_2023_paper",
        "21016": "Goyal_Finetune_Like_You_Pretrain_Improved_Finetuning_of_Zero-Shot_Vision_Models_CVPR_2023_paper",
        "21038_bPxqSEy": "Yun_IFSeg_Image-Free_Semantic_Segmentation_via_Vision-Language_Model_CVPR_2023_paper",
        "21051": "Cho_Implicit_3D_Human_Mesh_Recovery_Using_Consistency_With_Pose_and_CVPR_2023_paper",
        "21074": "Kim_Coreset_Sampling_From_Open-Set_for_Fine-Grained_Self-Supervised_Learning_CVPR_2023_paper",
        "21085": "Zhang_Object_Detection_With_Self-Supervised_Scene_Adaptation_CVPR_2023_paper",
        "21119": "Chen_A_Unified_Knowledge_Distillation_Framework_for_Deep_Directed_Graphical_Models_CVPR_2023_paper",
        "21172_Byz46Zl": "Guo_Knowledge_Distillation_for_6D_Pose_Estimation_by_Aligning_Distributions_of_CVPR_2023_paper",
        "21195": "Kong_Indescribable_Multi-Modal_Spatial_Evaluator_CVPR_2023_paper",
        "21207": "Huang_Contrastive_Semi-Supervised_Learning_for_Underwater_Image_Restoration_via_Reliable_Bank_CVPR_2023_paper",
        "21229_pL731AP": "Wang_Privacy-Preserving_Adversarial_Facial_Features_CVPR_2023_paper",
        "21247_gGSqs4l": "Liu_SynthVSR_Scaling_Up_Visual_Speech_Recognition_With_Synthetic_Supervision_CVPR_2023_paper",
        "21283": "Rivas-Manzaneque_NeRFLight_Fast_and_Light_Neural_Radiance_Fields_Using_a_Shared_CVPR_2023_paper",
        "21367": "Luo_Leverage_Interactive_Affinity_for_Affordance_Learning_CVPR_2023_paper",
        "21396_ciQM3yy": "Metaxas_DivClust_Controlling_Diversity_in_Deep_Clustering_CVPR_2023_paper",
        "21417_IGIX3um": "Rahman_Learning_Partial_Correlation_Based_Deep_Visual_Representation_for_Image_Classification_CVPR_2023_paper",
        "21433": "Simeoni_Unsupervised_Object_Localization_Observing_the_Background_To_Discover_Objects_CVPR_2023_paper",
        "21454": "Wang_VideoMAE_V2_Scaling_Video_Masked_Autoencoders_With_Dual_Masking_CVPR_2023_paper",
        "21480": "Shaharabany_Similarity_Maps_for_Self-Training_Weakly-Supervised_Phrase_Grounding_CVPR_2023_paper",
        "21504": "Kang_Benchmarking_Self-Supervised_Learning_on_Diverse_Pathology_Datasets_CVPR_2023_paper",
        "21511": "Liao_Adaptive_Channel_Sparsity_for_Federated_Learning_Under_System_Heterogeneity_CVPR_2023_paper",
        "21527": "Yu_How_To_Prevent_the_Continuous_Damage_of_Noises_To_Model_CVPR_2023_paper",
        "21541_uGvgrx3": "Kang_The_Dialog_Must_Go_On_Improving_Visual_Dialog_via_Generative_CVPR_2023_paper",
        "21588": "Zhao_Augmentation_Matters_A_Simple-Yet-Effective_Approach_to_Semi-Supervised_Semantic_Segmentation_CVPR_2023_paper",
        "21595": "Wang_Conflict-Based_Cross-View_Consistency_for_Semi-Supervised_Semantic_Segmentation_CVPR_2023_paper",
        "21645": "Pan_Fine-Grained_Image-Text_Matching_by_Cross-Modal_Hard_Aligning_Network_CVPR_2023_paper",
        "21659": "Liu_Pose-Disentangled_Contrastive_Learning_for_Self-Supervised_Facial_Representation_CVPR_2023_paper",
        "21679_i9lDAWg": "Kim_Generalizable_Implicit_Neural_Representations_via_Instance_Pattern_Composers_CVPR_2023_paper",
        "21720": "Li_Task-Specific_Fine-Tuning_via_Variational_Information_Bottleneck_for_Weakly-Supervised_Pathology_Whole_CVPR_2023_paper",
        "21747": "Wu_Sparsely_Annotated_Semantic_Segmentation_With_Adaptive_Gaussian_Mixtures_CVPR_2023_paper",
        "21770": "Jiao_Learning_Attribute_and_Class-Specific_Representation_Duet_for_Fine-Grained_Fashion_Analysis_CVPR_2023_paper",
        "21784": "He_Few-Shot_Geometry-Aware_Keypoint_Localization_CVPR_2023_paper",
        "21849": "Ren_Defining_and_Quantifying_the_Emergence_of_Sparse_Concepts_in_DNNs_CVPR_2023_paper",
        "21868_Jt5RFGs": "Kim_Grounding_Counterfactual_Explanation_of_Image_Classifiers_to_Textual_Concept_Space_CVPR_2023_paper",
        "21916_pKVrtUW": "Jiang_Color_Backdoor_A_Robust_Poisoning_Attack_in_Color_Space_CVPR_2023_paper",
        "21931": "Lin_Deep_Frequency_Filtering_for_Domain_Generalization_CVPR_2023_paper",
        "21961": "Li_PillarNeXt_Rethinking_Network_Designs_for_3D_Object_Detection_in_LiDAR_CVPR_2023_paper",
        "21962": "Cai_MARLIN_Masked_Autoencoder_for_Facial_Video_Representation_LearnINg_CVPR_2023_paper",
        "21964_whhGtwx": "Wang_Compacting_Binary_Neural_Networks_by_Sparse_Kernel_Selection_CVPR_2023_paper",
        "21989_SjCUYSy": "Deng_NeRDi_Single-View_NeRF_Synthesis_With_Language-Guided_Diffusion_As_General_Image_CVPR_2023_paper",
        "22016": "Singh_Polynomial_Implicit_Neural_Representations_for_Large_Diverse_Datasets_CVPR_2023_paper",
        "22035": "Boulch_ALSO_Automotive_Lidar_Self-Supervision_by_Occupancy_Estimation_CVPR_2023_paper",
        "22083": "Park_Multi-Modal_Representation_Learning_With_Text-Driven_Soft_Masks_CVPR_2023_paper",
        "22122": "Wang_Open-Set_Fine-Grained_Retrieval_via_Prompting_Vision-Language_Evaluator_CVPR_2023_paper",
        "22144": "Chen_Boosting_Semi-Supervised_Learning_by_Exploiting_All_Unlabeled_Data_CVPR_2023_paper",
        "22191": "Ye_Partial_Network_Cloning_CVPR_2023_paper",
        "22197_CyRzbzC": "Wang_Detecting_Everything_in_the_Open_World_Towards_Universal_Object_Detection_CVPR_2023_paper",
        "22201_ZYGCbfZ": "Sidhartha_Adaptive_Annealing_for_Robust_Geometric_Estimation_CVPR_2023_paper",
        "22223": "Borse_DejaVu_Conditional_Regenerative_Learning_To_Enhance_Dense_Prediction_CVPR_2023_paper",
        "22295": "Yang_RILS_Masked_Visual_Reconstruction_in_Language_Semantic_Space_CVPR_2023_paper",
        "22298": "Wang_Image_Cropping_With_Spatial-Aware_Feature_and_Rank_Consistency_CVPR_2023_paper",
        "22311": "Kalluri_GeoNet_Benchmarking_Unsupervised_Adaptation_Across_Geographies_CVPR_2023_paper",
        "22352": "Gosala_SkyEye_Self-Supervised_Birds-Eye-View_Semantic_Mapping_Using_Monocular_Frontal_View_Images_CVPR_2023_paper",
        "22361": "Liu_Exploring_the_Relationship_Between_Architectural_Design_and_Adversarially_Robust_Generalization_CVPR_2023_paper",
        "22404_vQy5TWM": "Chen_NeuralEditor_Editing_Neural_Radiance_Fields_via_Manipulating_Point_Clouds_CVPR_2023_paper",
        "22409_S9dYIsm": "Chen_Mixed_Autoencoder_for_Self-Supervised_Visual_Representation_Learning_CVPR_2023_paper",
        "22493": "Chen_VoxelNeXt_Fully_Sparse_VoxelNet_for_3D_Object_Detection_and_Tracking_CVPR_2023_paper",
        "22533": "Liu_PartSLIP_Low-Shot_Part_Segmentation_for_3D_Point_Clouds_via_Pretrained_CVPR_2023_paper",
        "22562_XDqg0kQ": "Zhang_Boosting_Video_Object_Segmentation_via_Space-Time_Correspondence_Learning_CVPR_2023_paper",
        "22568": "Yoshimura_Rawgment_Noise-Accounted_RAW_Augmentation_Enables_Recognition_in_a_Wide_Variety_CVPR_2023_paper",
        "22580": "Cao_Recurrent_Homography_Estimation_Using_Homography-Guided_Image_Warping_and_Focus_Transformer_CVPR_2023_paper",
        "22597": "Lee_Multimodal_Prompting_With_Missing_Modalities_for_Visual_Recognition_CVPR_2023_paper",
        "22641": "He_Align_and_Attend_Multimodal_Summarization_With_Dual_Contrastive_Losses_CVPR_2023_paper",
        "22695": "Li_Unified_Mask_Embedding_and_Correspondence_Learning_for_Self-Supervised_Video_Segmentation_CVPR_2023_paper",
        "22720": "Hu_Physically_Realizable_Natural-Looking_Clothing_Textures_Evade_Person_Detectors_via_3D_CVPR_2023_paper",
        "22779": "Lin_Supervised_Masked_Knowledge_Distillation_for_Few-Shot_Transformers_CVPR_2023_paper",
        "22803_GpcNDWv": "Chen_MobileNeRF_Exploiting_the_Polygon_Rasterization_Pipeline_for_Efficient_Neural_Field_CVPR_2023_paper",
        "22804": "Agro_Implicit_Occupancy_Flow_Fields_for_Perception_and_Prediction_in_Self-Driving_CVPR_2023_paper",
        "22856": "Sajjadi_RUST_Latent_Neural_Scene_Representations_From_Unposed_Imagery_CVPR_2023_paper",
        "22965": "Hu_A_Dynamic_Multi-Scale_Voxel_Flow_Network_for_Video_Prediction_CVPR_2023_paper",
        "23000": "Wang_Adaptive_Patch_Deformation_for_Textureless-Resilient_Multi-View_Stereo_CVPR_2023_paper",
        "23009": "Zou_CLOTH4D_A_Dataset_for_Clothed_Human_Reconstruction_CVPR_2023_paper",
        "23012": "Athar_TarViS_A_Unified_Approach_for_Target-Based_Video_Segmentation_CVPR_2023_paper",
        "23074": "Liang_HelixSurf_A_Robust_and_Efficient_Neural_Implicit_Surface_Learning_of_CVPR_2023_paper",
        "23087_NLVTKOr": "Wei_Joint_Token_Pruning_and_Squeezing_Towards_More_Aggressive_Compression_of_CVPR_2023_paper",
        "23104": "Arsomngern_Learning_Geometric-Aware_Properties_in_2D_Representation_Using_Lightweight_CAD_Models_CVPR_2023_paper",
        "23147": "Li_SHS-Net_Learning_Signed_Hyper_Surfaces_for_Oriented_Normal_Estimation_of_CVPR_2023_paper",
        "23149": "Cho_Generative_Bias_for_Robust_Visual_Question_Answering_CVPR_2023_paper",
        "23154": "Zhou_How_Can_Objects_Help_Action_Recognition_CVPR_2023_paper",
        "23158": "Han_FAME-ViL_Multi-Tasking_Vision-Language_Model_for_Heterogeneous_Fashion_Tasks_CVPR_2023_paper",
        "23176": "Fu_Learning_Semantic_Relationship_Among_Instances_for_Image-Text_Matching_CVPR_2023_paper",
        "23180": "Ruiz_DreamBooth_Fine_Tuning_Text-to-Image_Diffusion_Models_for_Subject-Driven_Generation_CVPR_2023_paper",
        "23254": "Wang_MoLo_Motion-Augmented_Long-Short_Contrastive_Learning_for_Few-Shot_Action_Recognition_CVPR_2023_paper",
        "23262": "Shi_Top-Down_Visual_Attention_From_Analysis_by_Synthesis_CVPR_2023_paper",
    },
    ("CVPR", "2024"): {
        "29177": "Tian_Holistic_Features_are_almost_Sufficient_for_Text-to-Video_Retrieval_CVPR_2024_paper",
        "29201_R1Co4wg": "Wang_RepViT_Revisiting_Mobile_CNN_From_ViT_Perspective_CVPR_2024_paper",
        "29265": "Qin_Noisy-Correspondence_Learning_for_Text-to-Image_Person_Re-identification_CVPR_2024_paper",
        "29862": "Asnani_ProMark_Proactive_Diffusion_Watermarking_for_Causal_Attribution_CVPR_2024_paper",
        "30527": "Zhao_Instance_Tracking_in_3D_Scenes_from_Egocentric_Videos_CVPR_2024_paper",
        "30905": "Wang_An_Aggregation-Free_Federated_Learning_for_Tackling_Data_Heterogeneity_CVPR_2024_paper",
        "31044_aApkDDq": "Goel_PAIR_Diffusion_A_Comprehensive_Multimodal_Object-Level_Image_Editor_CVPR_2024_paper",
        "31106": "Wang_Navigate_Beyond_Shortcuts_Debiased_Learning_Through_the_Lens_of_Neural_CVPR_2024_paper",
        "31481_zlggPC3": "Azad_Activity-Biometrics_Person_Identification_from_Daily_Activities_CVPR_2024_paper",
        "31482_8P8HEzM": "Yang_Makeup_Prior_Models_for_3D_Facial_Makeup_Estimation_and_Applications_CVPR_2024_paper",
        "31766": "Xiang_MaxQ_Multi-Axis_Query_for_NM_Sparsity_Network_CVPR_2024_paper",
    },
    ("CVPR", "2025"): {
        "32455": "Samira_Variance-Based_Membership_Inference_Attacks_Against_Large-Scale_Image_Captioning_Models_CVPR_2025_paper",
        "32499": "Wang_LinGen_Towards_High-Resolution_Minute-Length_Text-to-Video_Generation_with_Linear_Computational_Complexity_CVPR_2025_paper",
        "32592_jOoJysu": "Bergner_Token_Cropr_Faster_ViTs_for_Quite_a_Few_Tasks_CVPR_2025_paper",
        "32870": "Wang_Vision-Language_Model_IP_Protection_via_Prompt-based_Learning_CVPR_2025_paper",
        "33026": "Hu_DepthCrafter_Generating_Consistent_Long_Depth_Sequences_for_Open-world_Videos_CVPR_2025_paper",
        "33064": "Yang_FreeUV_Ground-Truth-Free_Realistic_Facial_UV_Texture_Recovery_via_Cross-Assembly_Inference_CVPR_2025_paper",
        "33937": "Wang_Scaling_up_Image_Segmentation_across_Data_and_Tasks_CVPR_2025_paper",
        "34298": "Xu_PICD_Versatile_Perceptual_Image_Compression_with_Diffusion_Rendering_CVPR_2025_paper",
        "34362": "Kumar_DynaMoDe-NeRF_Motion-aware_Deblurring_Neural_Radiance_Field_for_Dynamic_Scenes_CVPR_2025_paper",
        "35092": "Vincent_High_Temporal_Consistency_through_Semantic_Similarity_Propagation_in_Semi-Supervised_Video_CVPR_2025_paper",
    },
    ("ICML", "2023"): {
        "23566_KmYjwLG": "liu23e", "23695": "luo23d", "23770": "kim23u", "24182": "enguehard23a",
        "24242": "severo23a", "24659": "eiben23a", "24894": "lee23q", "25059": "park23b",
    },
    ("ICML", "2024"): {
        "32737": "zhang24bi", "32909": "zarifzadeh24a", "32917": "liu24bq", "33005": "jinnai24a",
        "33148": "juergens24a", "33178": "clarke24a", "33293": "sun24p", "33414": "li24ab",
        "33467": "fei24a", "33994_BCkkSko": "lv24d", "34042": "vyas24a", "34134": "wang24bk",
        "34150": "kim24u", "34294": "pei24d", "34638": "wang24az", "34700": "sun24n",
        "34782": "mariella24a", "34864": "wang24cr", "34865": "gui24a", "34866": "kim24j",
        "35115": "georgiev24a", "35120_3BLcYJf": "kim24x", "35161_XhhfRwM": "jeeveswaran24a",
    },
    ("ICML", "2025"): {
        "40171": "A0HtZM0MpZ", "43445": "zy7Jw91tdh", "43776_dKd22kS": "tYwKQMMjJA",
        "43941": "qOgKMqv9T7", "43961_QE4Koxe": "q7PAIE0z5p", "44018": "pI4AbQ7pg1",
        "44236_Ys6b4zh": "kl7SbPfBsB", "44333": "iouCP8zZQS", "44339": "ij0vj0BC72",
        "44556": "f21sRSRb1E", "44727": "biMO2gWsWS", "44876": "Z9BaaWDE0r",
        "45033": "WCkMkMcqpb", "45183_Yy64bly": "TJHhXzTcQe", "45253": "RyOpooIxDF",
        "45276": "RUip3cD66H", "45291": "RBZpAa27ls", "45469": "NzoZXju2bL",
        "45592": "LNfiFWccxn", "45601": "LCr6CIAEye", "45710_TyXCAN0": "J8YRdm39jn",
        "46165": "AXJnqocQpm", "46210": "9hd5WA6QCn", "46294": "82A81az3V5",
        "46479": "4UfRP8MopP", "46571": "2hbx3wG2I1", "46658": "10l1pGeOcK",
    },
}

SLIDE_HOST = {
    "ECCV": "https://eccv.ecva.net/media/eccv-{y}/Slides/{k}.pdf",
    "ICLR": "https://iclr.cc/media/iclr-{y}/Slides/{k}.pdf",
    "CVPR": "https://cvpr.thecvf.com/media/cvpr-{y}/Slides/{k}.pdf",
    "ICML": "https://icml.cc/media/icml-{y}/Slides/{k}.pdf",
}


def paper_pdf_url(conf: str, year: str, pid: str) -> str:
    """학회별 페이지 URL 규칙을 실제 PDF 주소로 변환한다."""
    if conf == "ECCV":
        return f"https://www.ecva.net/papers/eccv_2024/papers_ECCV/papers/{pid}.pdf"
    if conf == "CVPR":
        return f"https://openaccess.thecvf.com/content/CVPR{year}/papers/{pid}.pdf"
    if conf == "ICML" and year == "2023":
        return f"http://proceedings.mlr.press/v202/{pid}/{pid}.pdf"
    if conf == "ICML" and year == "2024":
        # PMLR v235부터 PDF는 GitHub(mlresearch)에서 서빙된다.
        return f"https://raw.githubusercontent.com/mlresearch/v235/main/assets/{pid}/{pid}.pdf"
    return f"https://openreview.net/pdf?id={pid}"  # ICLR 2024/2025, ICML 2025


def build_items():
    items = []
    for (conf, year), entries in DATA.items():
        for key, pid in entries.items():
            items.append({
                "id": f"{conf}{year}_{key}",
                "conference": conf,
                "year": year,
                "key": key,
                "paper_pdf_url": paper_pdf_url(conf, year, pid),
                "slides_pdf_url": SLIDE_HOST[conf].format(y=year, k=key),
            })
    return items


def fetch(url: str, dest: Path, retries: int = 3) -> str:
    if dest.exists() and dest.stat().st_size > 1024:
        return "skipped"
    # urllib는 ecva.net의 불완전한 인증서 체인을 검증하지 못해서 OS 인증서를 쓰는 curl을 사용한다.
    last = ""
    tmp = dest.with_suffix(".part")
    for attempt in range(retries):
        p = subprocess.run(
            ["curl", "-L", "-f", "-sS", "-m", "900", "--speed-time", "60", "--speed-limit", "20000",
             "-A", "Mozilla/5.0", "-o", str(tmp), url],
            capture_output=True, text=True,
        )
        if p.returncode == 0:
            if tmp.read_bytes()[:4] == b"%PDF":
                tmp.replace(dest)
                return "ok"
            last = "not a PDF"
        else:
            last = (p.stderr.strip().splitlines() or [f"curl {p.returncode}"])[-1][:80]
            if "404" in last or "403" in last:
                break
        time.sleep(2 * (attempt + 1))
    tmp.unlink(missing_ok=True)
    return f"failed: {last}"


def process(item):
    d = OUT / item["id"]
    d.mkdir(parents=True, exist_ok=True)
    item["paper_status"] = fetch(item["paper_pdf_url"], d / "paper.pdf")
    item["slides_status"] = fetch(item["slides_pdf_url"], d / "slides.pdf")
    print(f'{item["id"]:34s} paper={item["paper_status"]:22s} slides={item["slides_status"]}', flush=True)
    return item


def main():
    # 다운로드 완료 후 비활성화: examples/에는 paper.pdf + slides.pdf 쌍이 모두 있는 폴더만 남겼다.
    # 다시 받으려면 아래 두 줄을 지울 것.
    print("다운로드가 비활성화되어 있습니다. (scripts/download_examples.py main() 참고)")
    return

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    items = build_items()
    if args.limit:
        items = items[: args.limit]
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(process, items))

    manifest = OUT / "manifest.json"
    manifest.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    bad = [r for r in results if r["paper_status"].startswith("failed") or r["slides_status"].startswith("failed")]
    print(f"\n총 {len(results)}쌍, 실패 {len(bad)}쌍 -> {manifest}")


if __name__ == "__main__":
    main()
